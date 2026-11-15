"""Economy, prices, shortages, housing property, stealth, and city time events (GDD Sections 10, 11)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character


class EconomySystem:
    """Manages dynamic city economy, price index, housing property, stealth checks, and time events."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        clock: WorldClock | None = None,
        rng: SeededRNG | None = None,
        world: Any = None,
        **kwargs: Any,
    ) -> None:
        self.event_bus = event_bus
        self.clock = clock
        self.rng = rng
        self.world = world

    def _create_event(
        self,
        event_type: str,
        timestamp: int,
        source_id: str | None = None,
        target_ids: list[str] | None = None,
        location_id: str | None = None,
        data: dict[str, Any] | None = None,
        importance: float = 0.5,
        priority: EventPriority | str | None = None,
    ) -> GameEvent:
        if self.event_bus is not None and hasattr(self.event_bus, "create_event"):
            return self.event_bus.create_event(
                event_type=event_type,
                timestamp=timestamp,
                source_id=source_id,
                target_ids=target_ids,
                location_id=location_id,
                data=data,
                importance=importance,
                priority=priority,
            )
        self._fallback_event_seq = getattr(self, "_fallback_event_seq", 0) + 1
        return GameEvent(
            id=f"ev_econ_{self._fallback_event_seq:05d}",
            event_type=event_type,
            timestamp=timestamp,
            source_id=source_id,
            target_ids=list(target_ids) if target_ids else [],
            location_id=location_id,
            data=dict(data) if data else {},
            importance=importance,
            priority=priority.value if isinstance(priority, EventPriority) else (priority or "normal"),
        )

    def process_daily_tick(self, world: Any = None) -> dict[str, Any]:
        """Simulate daily market economy, price index, shortages, property income, loans, caravans, and Daily City Digest."""
        active_world = world or self.world
        if not active_world:
            return {"price_index": 1.0, "shortages": []}

        if not hasattr(active_world, "economy") or not isinstance(active_world.economy, dict):
            active_world.economy = {"price_index": 1.0, "shortages": [], "wages": 15.0}

        shortages: list[str] = []
        if hasattr(active_world, "districts"):
            for d in active_world.districts.values():
                if getattr(d, "food_supply", 50.0) < 30.0:
                    shortages.append("food")
                    break

        if shortages:
            active_world.economy["price_index"] = 1.45
            active_world.economy["shortages"] = shortages
        else:
            active_world.economy["price_index"] = 1.0
            active_world.economy["shortages"] = []

        # 1. Passive property income
        property_income = 0.0
        if hasattr(active_world, "properties") and isinstance(active_world.properties, dict):
            for prop in active_world.properties.values():
                if not isinstance(prop, dict):
                    continue
                owner_id = prop.get("owner")
                income = float(prop.get("daily_income", 0.0))
                if income > 0.0 and owner_id and hasattr(active_world, "characters"):
                    owner = active_world.characters.get(owner_id)
                    if owner is not None:
                        if not hasattr(owner, "needs") or owner.needs is None:
                            owner.needs = {}
                        owner.needs["wealth"] = float(owner.needs.get("wealth", 0.0)) + income
                        property_income += income

        # 2. Loans: daily interest & Syndicate enforcer default risk
        loan_interest_accrued = 0.0
        defaults: list[str] = []
        if hasattr(active_world, "loans") and isinstance(active_world.loans, list):
            for loan in active_world.loans:
                if not isinstance(loan, dict) or loan.get("status") != "active":
                    continue
                rate = float(loan.get("daily_interest_rate", 0.05))
                balance = float(loan.get("balance", 0.0))
                interest = round(balance * rate, 2)
                loan["balance"] = round(balance + interest, 2)
                loan_interest_accrued += interest
                loan["days_remaining"] = int(loan.get("days_remaining", 1)) - 1

                if loan["days_remaining"] <= 0 and loan["balance"] > 0.0:
                    loan["status"] = "defaulted"
                    defaults.append(str(loan.get("id", "loan")))
                    borrower_id = loan.get("borrower_id", "player")
                    borrower = (
                        active_world.characters.get(borrower_id)
                        if hasattr(active_world, "characters")
                        else None
                    )
                    if borrower is not None and hasattr(borrower, "needs"):
                        # Syndicate enforcers seize partial wealth or mark threat
                        seized = min(float(borrower.needs.get("wealth", 0.0)), round(loan["balance"] * 0.25, 2))
                        borrower.needs["wealth"] = max(0.0, float(borrower.needs.get("wealth", 0.0)) - seized)
                    if hasattr(active_world, "flags") and isinstance(active_world.flags, dict):
                        active_world.flags["syndicate_enforcer_dispatched"] = True
                        active_world.flags["defaulted_loans"] = list(
                            set(active_world.flags.get("defaulted_loans", [])) | set(defaults)
                        )
                    if self.event_bus:
                        self.event_bus.emit(
                            self._create_event(
                                event_type="LOAN_DEFAULTED",
                                timestamp=self.clock.timestamp if self.clock else 0,
                                source_id=str(loan.get("lender", "lowtown_syndicate")),
                                target_ids=[str(borrower_id)],
                                location_id="lowtown",
                                data={"loan_id": loan.get("id"), "balance": loan["balance"]},
                                importance=0.8,
                                priority=EventPriority.NORMAL,
                            ),
                            priority=EventPriority.NORMAL,
                        )

        # 3. Caravans: resolve maturing investments deterministically with world.rng
        caravan_returns = 0.0
        rng = getattr(active_world, "rng", None) or self.rng
        if hasattr(active_world, "caravans") and isinstance(active_world.caravans, list):
            for caravan in active_world.caravans:
                if not isinstance(caravan, dict) or caravan.get("status") != "in_transit":
                    continue
                caravan["days_remaining"] = int(caravan.get("days_remaining", 1)) - 1
                if caravan["days_remaining"] <= 0:
                    risk = float(caravan.get("risk", 0.15))
                    roll = rng.random("caravan") if rng is not None else 0.5
                    if roll < risk:
                        caravan["status"] = "raided"
                        caravan["payout"] = 0.0
                    else:
                        payout = round(float(caravan.get("expected_return", 0.0)), 2)
                        caravan["status"] = "completed"
                        caravan["payout"] = payout
                        investor_id = caravan.get("investor_id", "player")
                        investor = (
                            active_world.characters.get(investor_id)
                            if hasattr(active_world, "characters")
                            else None
                        )
                        if investor is not None:
                            investor.needs["wealth"] = float(investor.needs.get("wealth", 0.0)) + payout
                        caravan_returns += payout

        # 4. Daily City Digest
        current_day = int(active_world.clock.day) if getattr(active_world, "clock", None) else 1
        summary_lines = [
            f"Day {current_day} City Digest: Price Index {active_world.economy['price_index']:.2f}x",
        ]
        if shortages:
            summary_lines.append(f"Shortages reported: {', '.join(shortages)}")
        if property_income > 0.0:
            summary_lines.append(f"Property income collected: +{property_income:.1f}g")
        if loan_interest_accrued > 0.0:
            summary_lines.append(f"Loan interest accrued: {loan_interest_accrued:.1f}g")
        if defaults:
            summary_lines.append(f"WARNING: Loan default ({', '.join(defaults)}) — enforcers dispatched!")
        if caravan_returns > 0.0:
            summary_lines.append(f"Caravan returns: +{caravan_returns:.1f}g")

        digest = {
            "day": current_day,
            "price_index": float(active_world.economy["price_index"]),
            "shortages": list(shortages),
            "property_income": round(property_income, 2),
            "loan_interest_accrued": round(loan_interest_accrued, 2),
            "defaults": list(defaults),
            "caravan_returns": round(caravan_returns, 2),
            "summary_lines": summary_lines,
        }
        if hasattr(active_world, "flags") and isinstance(active_world.flags, dict):
            active_world.flags["last_daily_digest"] = digest

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="ECONOMY_UPDATED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=None,
                    target_ids=[],
                    location_id=None,
                    data=dict(active_world.economy),
                    importance=0.4,
                    priority=EventPriority.BACKGROUND,
                ),
                priority=EventPriority.BACKGROUND,
            )

        result = dict(active_world.economy)
        result["daily_digest"] = digest
        return result

    def update_economy(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.process_daily_tick(*args, **kwargs)

    def step_economy(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.process_daily_tick(*args, **kwargs)

    def acquire_property(
        self,
        char_id: str,
        property_id: str,
        cost: float = 0.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Allow character to purchase safehouse, workshop, or business property (GDD Section 11)."""
        from content import PROPERTIES_CATALOG

        active_world = world or self.world
        char = active_world.characters.get(char_id) if active_world and hasattr(active_world, "characters") else None
        cost_val = max(0.0, float(cost))

        if cost_val > 0.0:
            wealth = float(char.needs.get("wealth", 0.0)) if char else 0.0
            if char is None or wealth < cost_val:
                return {
                    "success": False,
                    "reason": "insufficient_wealth",
                    "property_id": property_id,
                    "owner": char_id,
                    "cost": cost_val,
                    "wealth": wealth,
                }
            char.needs["wealth"] = max(0.0, wealth - cost_val)

        catalog_entry = PROPERTIES_CATALOG.get(property_id, {})
        prop_data = {
            "success": True,
            "property_id": property_id,
            "name": catalog_entry.get("name", property_id),
            "district_id": catalog_entry.get("district_id", "lowtown"),
            "owner": char_id,
            "type": catalog_entry.get("type", "safehouse" if "safehouse" in property_id else "business"),
            "cost": cost_val,
            "level": 1,
            "daily_income": float(catalog_entry.get("daily_income", 15.0)),
            "purchased_at": self.clock.timestamp if self.clock else 0,
        }

        if active_world and hasattr(active_world, "properties"):
            active_world.properties[property_id] = prop_data

        return prop_data

    def buy_property(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.acquire_property(*args, **kwargs)

    def purchase_housing(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.acquire_property(*args, **kwargs)

    def upgrade_property(
        self,
        char_id: str,
        property_id: str,
        world: Any = None,
    ) -> dict[str, Any]:
        """Upgrade an owned property to increase daily passive income."""
        from content import PROPERTIES_CATALOG

        active_world = world or self.world
        if not active_world or not hasattr(active_world, "properties"):
            return {"success": False, "reason": "no_world"}

        prop = active_world.properties.get(property_id)
        if not prop or prop.get("owner") != char_id:
            return {"success": False, "reason": "not_owned", "property_id": property_id}

        char = active_world.characters.get(char_id) if hasattr(active_world, "characters") else None
        if char is None:
            return {"success": False, "reason": "no_character"}

        current_level = int(prop.get("level", 1))
        catalog_entry = PROPERTIES_CATALOG.get(property_id, {})
        base_upgrade = float(catalog_entry.get("upgrade_base_cost", 120.0))
        upgrade_cost = round(base_upgrade * current_level, 2)
        wealth = float(char.needs.get("wealth", 0.0))
        if wealth < upgrade_cost:
            return {
                "success": False,
                "reason": "insufficient_wealth",
                "cost": upgrade_cost,
                "wealth": wealth,
            }

        char.needs["wealth"] = max(0.0, wealth - upgrade_cost)
        income_boost = float(catalog_entry.get("income_per_level", 15.0))
        prop["level"] = current_level + 1
        prop["daily_income"] = float(prop.get("daily_income", 15.0)) + income_boost

        return {
            "success": True,
            "property_id": property_id,
            "level": prop["level"],
            "daily_income": prop["daily_income"],
            "cost": upgrade_cost,
        }

    def get_commodity_price(
        self,
        commodity_id: str,
        district_id: str = "lowtown",
        world: Any = None,
    ) -> float:
        """Calculate dynamic district commodity price based on food_supply, wealth, crime, unrest, and embargoes."""
        from content import COMMODITIES

        active_world = world or self.world
        spec = COMMODITIES.get(commodity_id)
        if not spec:
            raise ValueError(f"Unknown commodity: {commodity_id}")

        price = float(spec["base_price"])
        if active_world is None:
            return round(price, 2)

        global_idx = float(getattr(active_world, "economy", {}).get("price_index", 1.0))
        price *= global_idx

        district = active_world.districts.get(district_id) if hasattr(active_world, "districts") else None
        if district is not None:
            food = float(getattr(district, "food_supply", 50.0))
            wealth = float(getattr(district, "wealth", 50.0))
            crime = float(getattr(district, "crime", 30.0))
            unrest = float(getattr(district, "unrest", 30.0))
            security = float(getattr(district, "security", 50.0))

            if commodity_id == "grain_rations":
                price *= max(0.6, 1.5 - (food / 100.0))
            elif commodity_id == "iron_tools":
                price *= 0.8 if district_id == "iron_ward" else 1.05 + (wealth / 400.0)
            elif commodity_id == "weapons_armor":
                price *= 1.0 + (unrest / 200.0) + (crime / 250.0)
            elif commodity_id == "medical_supplies":
                price *= 1.0 + (unrest / 180.0) + max(0.0, (50.0 - food) / 150.0)
            elif commodity_id == "luxury_silk_wine":
                price *= 0.75 + (wealth / 120.0)
            elif commodity_id == "smuggled_contraband":
                price *= max(0.65, 1.35 + (security - crime) / 150.0)

        embargoes = getattr(active_world, "flags", {}).get("embargoes", {})
        if isinstance(embargoes, dict) and (district_id in embargoes or commodity_id in embargoes):
            price *= 1.35

        return round(max(1.0, price), 2)

    def buy_commodity(
        self,
        char_id: str,
        commodity_id: str,
        quantity: int = 1,
        district_id: str = "lowtown",
        world: Any = None,
    ) -> dict[str, Any]:
        """Purchase commodity units at dynamic district price."""
        active_world = world or self.world
        qty = max(1, int(quantity))
        if not active_world:
            return {"success": False, "reason": "no_world"}

        char = active_world.characters.get(char_id)
        if char is None:
            return {"success": False, "reason": "no_character"}

        unit_price = self.get_commodity_price(commodity_id, district_id=district_id, world=active_world)
        total_cost = round(unit_price * qty, 2)
        wealth = float(char.needs.get("wealth", 0.0))
        if wealth < total_cost:
            return {
                "success": False,
                "reason": "insufficient_wealth",
                "total_cost": total_cost,
                "wealth": wealth,
            }

        char.needs["wealth"] = max(0.0, wealth - total_cost)
        if not hasattr(active_world, "commodities") or not isinstance(active_world.commodities, dict):
            active_world.commodities = {}
        active_world.commodities[commodity_id] = int(active_world.commodities.get(commodity_id, 0)) + qty

        return {
            "success": True,
            "commodity_id": commodity_id,
            "quantity": qty,
            "unit_price": unit_price,
            "total_cost": total_cost,
            "owned": active_world.commodities[commodity_id],
        }

    def sell_commodity(
        self,
        char_id: str,
        commodity_id: str,
        quantity: int = 1,
        district_id: str = "lowtown",
        world: Any = None,
    ) -> dict[str, Any]:
        """Sell owned commodity units at dynamic district price."""
        active_world = world or self.world
        qty = max(1, int(quantity))
        if not active_world:
            return {"success": False, "reason": "no_world"}

        char = active_world.characters.get(char_id)
        if char is None:
            return {"success": False, "reason": "no_character"}

        owned = int(getattr(active_world, "commodities", {}).get(commodity_id, 0))
        if owned < qty:
            return {"success": False, "reason": "insufficient_stock", "owned": owned, "requested": qty}

        unit_price = self.get_commodity_price(commodity_id, district_id=district_id, world=active_world)
        revenue = round(unit_price * qty, 2)
        active_world.commodities[commodity_id] = owned - qty
        char.needs["wealth"] = float(char.needs.get("wealth", 0.0)) + revenue

        return {
            "success": True,
            "commodity_id": commodity_id,
            "quantity": qty,
            "unit_price": unit_price,
            "revenue": revenue,
            "remaining": active_world.commodities[commodity_id],
        }

    def take_loan(
        self,
        char_id: str,
        amount: float,
        lender: str = "merchant_consortium",
        term_days: int = 7,
        world: Any = None,
    ) -> dict[str, Any]:
        """Take a loan from the Consortium or Lowtown Syndicate."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        char = active_world.characters.get(char_id)
        if char is None:
            return {"success": False, "reason": "no_character"}

        principal = max(10.0, float(amount))
        rate = 0.10 if "syndicate" in lender else 0.05
        if not hasattr(active_world, "loans") or not isinstance(active_world.loans, list):
            active_world.loans = []

        rng = getattr(active_world, "rng", None) or self.rng
        suffix = rng.randint("loan", 1000, 9999) if rng is not None else len(active_world.loans) + 1
        loan_id = f"loan_{len(active_world.loans) + 1}_{suffix}"
        loan = {
            "id": loan_id,
            "borrower_id": char_id,
            "lender": lender,
            "principal": principal,
            "balance": principal,
            "daily_interest_rate": rate,
            "days_remaining": max(1, int(term_days)),
            "status": "active",
        }
        active_world.loans.append(loan)
        char.needs["wealth"] = float(char.needs.get("wealth", 0.0)) + principal

        return {"success": True, "loan": dict(loan)}

    def repay_loan(
        self,
        char_id: str,
        loan_id: str,
        amount: float | None = None,
        world: Any = None,
    ) -> dict[str, Any]:
        """Repay an active or defaulted loan."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        char = active_world.characters.get(char_id)
        if char is None:
            return {"success": False, "reason": "no_character"}

        loan = next((l for l in getattr(active_world, "loans", []) if l.get("id") == loan_id), None)
        if loan is None or loan.get("status") == "paid":
            return {"success": False, "reason": "loan_not_found_or_paid"}

        balance = float(loan.get("balance", 0.0))
        pay_amount = balance if amount is None else min(balance, max(0.0, float(amount)))
        wealth = float(char.needs.get("wealth", 0.0))
        if wealth < pay_amount:
            return {"success": False, "reason": "insufficient_wealth", "needed": pay_amount, "wealth": wealth}

        char.needs["wealth"] = max(0.0, wealth - pay_amount)
        loan["balance"] = round(max(0.0, balance - pay_amount), 2)
        if loan["balance"] <= 0.0:
            loan["status"] = "paid"

        return {"success": True, "loan_id": loan_id, "paid": pay_amount, "balance": loan["balance"], "status": loan["status"]}

    def invest_caravan(
        self,
        char_id: str,
        amount: float,
        route: str = "harbor_to_high_quarter",
        world: Any = None,
    ) -> dict[str, Any]:
        """Invest gold in a merchant caravan with deterministic risk/return resolved on daily ticks."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        char = active_world.characters.get(char_id)
        if char is None:
            return {"success": False, "reason": "no_character"}

        invest_amt = max(10.0, float(amount))
        wealth = float(char.needs.get("wealth", 0.0))
        if wealth < invest_amt:
            return {"success": False, "reason": "insufficient_wealth", "cost": invest_amt, "wealth": wealth}

        char.needs["wealth"] = max(0.0, wealth - invest_amt)
        if not hasattr(active_world, "caravans") or not isinstance(active_world.caravans, list):
            active_world.caravans = []

        rng = getattr(active_world, "rng", None) or self.rng
        suffix = rng.randint("caravan", 1000, 9999) if rng is not None else len(active_world.caravans) + 1
        caravan = {
            "id": f"caravan_{len(active_world.caravans) + 1}_{suffix}",
            "investor_id": char_id,
            "route": route,
            "invested": invest_amt,
            "expected_return": round(invest_amt * 1.35, 2),
            "risk": 0.15,
            "days_remaining": 3,
            "status": "in_transit",
            "payout": 0.0,
        }
        active_world.caravans.append(caravan)
        return {"success": True, "caravan": dict(caravan)}

    def trigger_time_event(
        self,
        event_kind: str,
        district_id: str,
        world: Any = None,
    ) -> dict[str, Any]:
        """Trigger major city time event (elections, wars, festivals, riots) (GDD Section 11)."""
        active_world = world or self.world
        district = active_world.districts.get(district_id) if active_world and hasattr(active_world, "districts") else None

        if district:
            if event_kind == "riot":
                district.unrest = min(100.0, district.unrest + 30.0)
                district.security = max(0.0, district.security - 20.0)
            elif event_kind == "festival":
                district.unrest = max(0.0, district.unrest - 20.0)
            elif event_kind == "war":
                district.security = max(0.0, district.security - 35.0)

        ev_data = {
            "event_kind": event_kind,
            "district_id": district_id,
            "description": f"A major {event_kind} erupted in {district_id}!",
        }

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="TIME_EVENT_TRIGGERED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=None,
                    target_ids=[district_id],
                    location_id=district_id,
                    data=ev_data,
                    importance=0.85,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return ev_data

    def evaluate_time_events(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.trigger_time_event(*args, **kwargs)

    def calculate_stealth_check(
        self,
        character: Character,
        location_id: str = "lowtown_street",
    ) -> dict[str, float]:
        """Calculate stealth rating and suspicion score influenced by armor weight (GDD Section 11)."""
        skills = getattr(character, "skills", {}) or {}
        stealth_base = float(skills.get("stealth", 30.0))

        # Check armor encumbrance
        equipment = getattr(character, "equipment", {}) or {}
        armor_penalty = 0.0
        for item_name in equipment.values():
            if "plate" in str(item_name):
                armor_penalty += 45.0
            elif "chainmail" in str(item_name):
                armor_penalty += 25.0
            elif "leather" in str(item_name):
                armor_penalty += 5.0

        stealth_score = max(5.0, stealth_base - armor_penalty)
        suspicion = max(5.0, 100.0 - stealth_score)

        return {
            "stealth_score": stealth_score,
            "suspicion": suspicion,
        }

    def evaluate_stealth(self, *args: Any, **kwargs: Any) -> dict[str, float]:
        return self.calculate_stealth_check(*args, **kwargs)
