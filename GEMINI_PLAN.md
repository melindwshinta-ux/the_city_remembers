# THE CITY REMEMBERS — VEYR: WARSIM-STYLE CHOICE OVERHAUL & SYSTEMIC DEPTH PLAN

## 0. Context & Non-Negotiable Constraints
- **Repository**: `/home/antigravity/the_city_remembers`
- **Test Runner**: `/home/antigravity/the_city_remembers/.venv/bin/pytest`
- **Backward Compatibility**: All existing **346 unit and E2E tests MUST continue to pass (100%)**. Keep `Game.execute_command()`, `Game.parse_command()`, and existing system methods intact while layering the new *Warsim*-style `1`–`0` choice architecture on top.
- **Zero Typing Required**: The player must be able to play the entire game from Title Screen to Endgame using **only number keys `1`–`9` and `0`** (plus full mouse click support on every numbered option). Remove/hide the freeform text input box in normal play.
- **Deterministic Simulation**: Maintain seeded RNG (`SeededRNG`) and deterministic event propagation across all new features (no `uuid.uuid4()` in simulation events).

---

## 1. Title Screen, Main Menu, Settings & Difficulty (`ui/title_screen.py`, `core/settings.py`)

### 1.1 Main Menu (`1`–`5`, `0`)
Launch into an atmospheric ASCII/Rich Title Screen (`THE CITY REMEMBERS — VEYR`) controlled via keys `1`–`5` and `0` (and mouse clicks):
- `[1] Continue` — Loads the most recent save / `autosave` slot (displays character name, epithet, Year/Day, District, Gold, and Difficulty; gracefully disabled/dimmed if no save exists).
- `[2] New Game` — Opens the **New Game Setup** wizard (`1`–`0`):
  1. **Difficulty Selection**:
     - `[1] Story (Forgiving)`: +20% skill/dialogue check bonus, -30% incoming combat damage, +50% faster healing, +25% gold rewards, lower infection risk.
     - `[2] Balanced (Normal)`: Standard GDD simulation rules (100% baseline).
     - `[3] Gritty (Hard)`: -10% skill checks, +25% enemy damage, faster Nemesis adaptation, +20% market prices, stricter guard suspicion.
     - `[4] Ironman Veyr (Brutal)`: Gritty rules + single auto-saving slot (no manual reload scumming) + higher vital organ trauma risk.
  2. **Rowan's Background / Origin** (`[1]`–`[4]`):
     - `[1] Discharged Watch Veteran` (+Swordsmanship, +Discipline, +City Guard reputation)
     - `[2] Dockside Smuggler` (+Stealth, +Deception, +Lowtown Syndicate reputation)
     - `[3] Disgraced Noble Scion` (+Persuasion, +Leadership, +Noble Houses reputation)
     - `[4] Field Chirurgeon` (+Medicine, +Intelligence, starts with Surgeon's Kit)
  3. **Starting Keepsake** (`[1]`–`[4]`):
     - `[1] Heavy Coin Purse (+100 Gold)`
     - `[2] Fine Steel Longsword`
     - `[3] Forged Guild Seal (+Merchant & Guard Standing)`
     - `[4] Chirurgeon's Satchel (Bandages & Tonics)`
  4. **Onboarding Mode**:
     - `[1] Begin with Interactive Prologue`
     - `[2] Skip Prologue & Start in Act I (Lowtown)`
- `[3] Load Game` — Numbered slot browser `[1]`–`[8]` showing slot name, Act/Year, Location, Gold, Difficulty, and timestamp; `[9] Delete Slot`; `[0] Back`.
- `[4] Settings` — Persisted in `saves/settings.json` and synchronized with `game.settings`:
  - `[1] Difficulty`: Cycle `Story` / `Balanced` / `Gritty` / `Ironman`
  - `[2] Enable Cheat / Debug Mode`: `OFF` (default) / `ON` (**CRITICAL RULE: Cheat/Debug menu in-game MUST be inaccessible and hidden unless enabled here first!**)
  - `[3] Auto-Save`: `Every Day & Pre-Combat` / `Pre-Combat Only` / `Off`
  - `[4] Guided Tutorial HUD`: `ON` / `OFF`
  - `[5] Layout Mode`: `Auto` / `Compact (80x24)` / `Standard`
  - `[0] Save & Return`
- `[5] About & Controls Guide` — Displays game vision, inspirations (*Warsim*, *Dragon Age 2*, *RimWorld*, *Shadow of Mordor*), `1`–`0` controls guide, and simulation overview (`[0] Back`).
- `[0] Quit Game` — Confirms and exits cleanly.

---

## 2. *Warsim*-Style `1`–`0` Choice Engine & Zero-Typing UI (`core/menu_engine.py`, `main.py`)

### 2.1 Hierarchical Numbered Menu System
- Replace freeform command typing with a stack-based context menu engine where **every screen** presents up to 9 numbered actions (`[1]`–`[9]`) and `[0] Back / Leave / Cancel`.
- Pressing keys `1`–`9` or `0` on the keyboard—or clicking the corresponding button with the mouse—immediately executes that option or navigates into its sub-menu.
- **Standardized Key Conventions**:
  - `[1]`–`[8]`: Contextual choices / actions on the active screen.
  - `[9]`: `Next Page / More Options` (when a list has >8 items) or `System & Settings Menu` on the Root Hub.
  - `[0]`: Always `Back / Return / Leave` inside sub-menus, or `[0] Debug & Cheat Menu` on the Root Hub (only visible/enabled when `settings.enable_debug_cheat == True`).

### 2.2 Root Hub Menu (`[1]`–`[9]`, `[0]`)
When in Exploration / Hub mode, present:
- `[1] Travel & Explore District` — Connected local exits, district fast-travel, inspect local landmarks/crime scenes.
- `[2] Speak with Someone Nearby` — Lists NPCs and companions at the current location; selecting one launches **Interactive Dialogue Mode**.
- `[3] Local Activities & Establishments` — Context-sensitive actions for current location:
  - *Tavern*: Buy round for rumors, play Bones/Dice wager, take bounties/contracts, hear petitioners.
  - *Market / Workshop*: Buy/sell commodities, craft/upgrade gear, visit apothecary/surgeon.
  - *Safehouse / Camp*: Rest, hold court / hear visitors, manage stash.
- `[4] Party, Anatomy & Medicine` — Inspect 29-part body health, apply 5-stage medical treatments (`First Aid`, `Field Treatment`, `Surgery`, `Rehabilitation`, `Prosthetics`), manage equipment, talk/counsel with companions.
- `[5] Faction Politics & Nemesis Board` — View the 7 factions, inspect the 5-rank Nemesis hierarchy (`Recruit` -> `Leader`), request audiences, bribe, blackmail, fund edicts, or incite conflicts.
- `[6] Trade, Property & Economy` — Commodity market arbitrage, buy/upgrade businesses & workshops, smuggling operations, underworld loans.
- `[7] Quests, Rumors & City Chronicle` — Active mission objectives, resolve scenario approaches, plant/spread rumors, view Legacy & Chronicle history.
- `[8] Character Sheet & Reputation` — Rowan's attributes, skills, personality, dynamic epithets/titles, and 6-scope reputation bars.
- `[9] System, Save / Load & Settings` — Save/Load slots, Load Last Checkpoint, toggle Settings (including enabling/disabling Cheat/Debug Mode and Difficulty), Main Menu, Quit.
- `[0] Cheat & Debug Menu` — Only shown/unlocked when **Enable Cheat / Debug Mode** is set to `ON` in Settings (otherwise `[0] Pass Time / Rest & City Digest`).

### 2.3 Inline Odds, Costs & Consequence Previews
- Every numbered option must display clear inline metadata tags where applicable:
  - Skill check probability: `[Persuade 78%]`, `[Intimidate 45%]`, `[Stealth 65%]` (scaled by Difficulty).
  - Resource/Time costs: `[Cost: 50g]`, `[15m]`, `[8h]`.
  - Consequence hints: `[+Trust]`, `[+Fear, Risk: Combat]`, `[+Guard Rep]`.
  - Locked requirement explanations: `[Locked: Requires 50 Gold]`.

---

## 3. Interactive Branching Dialogue on Talk (`core/dialogue_engine.py`)

When the player selects an NPC via `[2] Speak with Someone Nearby` (or `talk <npc>`), enter **Interactive Dialogue Mode**:
- **Dialogue Header**: Shows NPC Name, Title/Rank, Faction, Visible Injuries/Scars (e.g., *Left Leg in Splints*), Relationship State (`Loyal associate`, `Respected rival`, `Bitter enemy`), and 6-axis bars (`Trust`, `Respect`, `Affection`, `Resentment`, `Fear`, `Dependency`).
- **Dynamic Greeting**: Reacts to past memories, injuries inflicted by the player, recent rumors, and Rowan's dynamic title/reputation.
- **Branching Numbered Choices (`[1]`–`[8]`, `[0]`)**:
  - `[1] Ask about local rumors & city news` — Reveals active district rumors, records into `MemorySystem`.
  - `[2] Discuss Mission / Quest Business` — Context-sensitive quest progression (e.g., *Blood in Lowtown* evidence, faction deals, missing apprentice).
  - `[3] [Persuade X%] Build Rapport / Reason with them` — Uses `persuasion`/`empathy` to raise `trust` and `affection` or gain cooperation.
  - `[4] [Intimidate X%] Threaten / Demand Compliance` — Uses `intimidation` + combat reputation to raise `fear`, extract info/coin, or force concessions (failure raises `resentment`/hostility).
  - `[5] [Cost: 25g] Offer Gift or Bribe` — Spends wealth to boost `trust`/`dependency` or drop guard suspicion.
  - `[6] [Companion Action]` — If a companion (`Sera`, `Marcus`, `Elira`, `Tomas`) is in the party, they interject and offer a specialized action (e.g., *"[Sera] Use underworld cant"*, *"[Marcus] Pull Watch rank"*, *"[Elira] Sense arcane residue"*).
  - `[7] Call in a Favor / Special Interaction` — Request faction backup, trade goods, or recruit/dismiss companion.
  - `[8] Provoke / Attack` — Transitions directly into Simplified Combat.
  - `[0] Leave Conversation` — Returns to the previous hub.

---

## 4. Simplified, Fast-Paced Combat (`systems/combat_system.py`, `ui/combat_screen.py`)

Replace the complex 21-command 5×5 grid micro with a **Streamlined *Warsim* / *Battle Brothers* Clash Interface** while keeping all underlying CombatSystem methods intact for existing tests:
- **Clear Clash Viewport**:
  - Side-by-side status of **Rowan & Party** vs. **Enemies** showing Consciousness %, Morale State (`Confident` -> `Routing`), Equipped Weapon/Armor, and Active Anatomical Wounds (`Bleeding`, `Broken Arm`, `Concussion`).
  - Rolling 5-line **Combat Narrative Log** describing clashes, armor mitigation, limb hits, and morale breaks.
- **Numbered Combat Choices (`[1]`–`[7]`, `[0]`)**:
  - `[1] Balanced Strike` — Standard attack with solid defense.
  - `[2] Heavy Brutal Assault` — High damage and armor penetration (`+35% dmg`), lower defense this round.
  - `[3] Aimed Limb / Organ Strike` — Opens quick sub-choice:
    - `[1] Head (Concussion / Blindness — Lower Accuracy)`
    - `[2] Arms (Fracture / Disarm — Cripple Enemy Attack)`
    - `[3] Torso (Internal Bleeding / Organ Trauma)`
    - `[4] Legs (Cripple Mobility / Prevent Escape)`
    - `[0] Back`
  - `[4] Defensive Stance & Rally Party` — Halves incoming damage, boosts party morale, protects wounded allies.
  - `[5] Field Triage & Bandage` — Stop bleeding and restore consciousness/pain tolerance mid-fight.
  - `[6] Tactical Trick / Arcane Surge` — Dirty fighting (throw dust/disarm) or companion spell/flank.
  - `[7] Demand Surrender / Intimidate` — Force frightened/routing enemies (`morale <= 30`) to yield without further bloodshed.
  - `[0] Retreat / Surrender` — Attempt escape or non-lethal surrender (Kenshi-style capture/imprisonment/robbery rather than instant game over).

---

## 5. Deep Political, Relationship & Economic Gameplay

### 5.1 Political Intrigue (`systems/faction_system.py`)
Add interactive player-driven political operations accessible from `[5] Faction Politics & Nemesis Board`:
- **Faction Audience & Diplomacy**:
  - `[1] Petition Faction Leader for Support / Contract`
  - `[2] Donate / Fund Faction Treasury (+Legitimacy, +Faction Rep)`
  - `[3] Broker Truce or Incite Turf War between Factions`
  - `[4] Pay Off City Guard Bounty / Clear Record`
- **Covert & District Operations**:
  - `[5] Plant False Rumor / Smear Campaign` (targets a faction or Nemesis officer)
  - `[6] Sabotage District Infrastructure / Incite Unrest or Strike`
  - `[7] Sponsor District Civic Edict` (*Soup Kitchens* `+Food/+Opinion`, *Private Watch Patrols* `+Security/-Crime`, *Festival* `-Unrest`)
  - `[8] Back Internal Coup / Bribe Subordinate to Betray Superior` (leverages `AmbitionAI` and `NemesisSystem` promotions)
- **Hold Court / Hear Petitioners**:
  - When resting at a Safehouse or Tavern, allow the player to hear `1`–`3` procedural petitioners (merchants, informants, desperate citizens, faction envoys) and judge their requests with `[1]`–`[4]`.

### 5.2 Relationship Depth (`systems/relationship_system.py`)
- **Direct Social Actions**:
  - Give gifts / share loot (`+Affection`, `+Trust`).
  - Extort / Blackmail fearful or compromised NPCs (`Fear >= 50` or secret memory known -> recurring gold/intel, `+Resentment`).
  - Companion Campfire Counsel: Ask companions for their perspective on current quests, factions, and rivalries; resolve companion breaking-point tensions before they depart.
  - Swear Blood Oath (high Trust/Respect) or Declare Open Blood Feud (Nemesis).

### 5.3 Economic & Property Depth (`systems/economy_system.py`)
- **District Commodity Market (`[6] Trade, Property & Economy`)**:
  - Buy and sell 6 core commodities across districts: `Grain & Rations`, `Iron & Tools`, `Weapons & Armor`, `Medical Supplies`, `Luxury Silk & Wine`, and `Smuggled Contraband`.
  - Prices dynamically reflect district `food_supply`, `wealth`, `crime`, `unrest`, and faction embargoes (enabling profitable merchant or smuggler playstyles).
- **Income-Generating Properties & Upgrades**:
  - Buy and upgrade properties (*Lowtown Safehouse*, *Cobblestone Stall*, *Iron Ward Smithy*, *Harbor Smuggler's Berth*, *Back-Alley Clinic*).
  - Properties generate daily passive gold during the **Daily City Digest**, reduce need decay, and unlock special local actions.
- **Consortium & Syndicate Finance**:
  - Take loans or invest in merchant caravans (with daily interest and Syndicate enforcers if defaulted).

---

## 6. Settings-Gated Debug & Cheat Mode (`core/debug_mode.py`)

- **Strict Gating Rule**:
  - `Debug / Cheat Mode` is **disabled by default** (`settings.enable_debug_cheat = False`).
  - Attempting to invoke any debug/cheat action while disabled returns a clear notice: `"Cheat/Debug Mode is disabled. Enable it in Settings first."`
  - Once enabled in Settings (`Main Menu -> [4] Settings -> [2] Enable Cheat / Debug Mode: ON` or `In-Game -> [9] System -> Settings`), `[0] Debug & Cheat Menu` becomes active.
- **Numbered Cheat / Debug Menu (`[1]`–`[9]`, `[0]`)**:
  - `[1] +500 Gold (Wealth)`
  - `[2] Full Heal & Cure All Anatomical Wounds (Player & Party)`
  - `[3] Max All Attributes & Skills (Set to 100)`
  - `[4] Toggle God Mode (Invulnerable + 100% Skill/Hit Success)`
  - `[5] Time Skip Menu (+6 Hours / +1 Day / +7 Days / +1 Year)`
  - `[6] Faction & District Manipulation (+25% Influence / Max All Faction Rep / Trigger Riot or Festival)`
  - `[7] Relationship Manipulation (+50 Trust, Respect & Affection with All Characters)`
  - `[8] Nemesis Manipulation (Spawn Nemesis / Force Promotion / Injure Voss)`
  - `[9] Quest & Tutorial Skip (Auto-Complete Current Tutorial Step or Scenario)`
  - `[0] Back to Game`

---

## 7. UI & UX Best Practices (`main.py`, `ui/`)

- **Clean *Warsim*-Style Framed Layout**:
  - **Top Status Banner**: `Act & Date/Time | Location (District) | Gold | Health/Consciousness | Difficulty | Active Epithet`.
  - **Collapsible Objective / Tutorial Banner**: Shows current guided mission step (`1`–`9`) with 1-key or 1-click completion.
  - **Main Narrative & Context Viewport**: Crisp Rich-formatted panels showing location/dialogue/combat/political details and the immediate outcome of the player's last choice.
  - **Numbered Action Deck (`[1]`–`[9]`, `[0]`)**: Clean, high-contrast numbered choice buttons at the bottom of the screen. Pressing `1`–`9` or `0` on the keyboard or clicking any button with the mouse triggers the choice immediately.
  - **Compact Terminal Support (`80x24`)**: Ensure all menus and screens remain readable and clickable at both `120x40` and `80x24`.

---

## 8. Verification & Testing Requirements
1. **Zero Regressions**: All existing **346 tests** (`tests/test_*.py` and `tests/e2e/test_*.py`) must pass without failure.
2. **New Unit & E2E Tests**:
   - Main Menu (`Continue`, `New Game`, `Load Game`, `Settings`, `About`), Difficulty modifiers, and Background/Keepsake selection.
   - Settings-gated Cheat/Debug Mode (verify blocked when `OFF`, verify all 9 cheat actions work when `ON`).
   - *Warsim* `1`–`0` Menu Engine navigation (keyboard `1`–`0` presses and mouse clicks with zero typing).
   - Interactive Branching Dialogue on Talk (persuasion, intimidation, bribe, companion interjection, rumor inquiry).
   - Simplified Combat choices (`[1]`–`[7]`, `[0]`) and anatomical wound integration.
   - Political operations, Relationship actions, and Economic commodity trading / property income.
