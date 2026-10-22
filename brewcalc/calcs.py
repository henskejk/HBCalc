"""Brewing formulas, ported from BrewingCalculator_JKH.xlsx.

Everything here is plain Python with no UI or database code, so it can be
tested on its own. Units follow the spreadsheet: gallons, pounds, ounces, °F.

Differences from the spreadsheet are marked "FIX:" below.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

# Hop form multiplier for Tinseth utilization ('Hops Reference'!D7:E8).
HOP_FORM_FACTOR = {"pellet": 1.1, "leaf": 1.0}

# Hop uses. A hop line's "minutes" field holds its time in the unit for that use (HOP_TIME_UNIT):
# minutes for everything except dry hops, which are in days.
HOP_USES = ["boil", "first wort", "flameout", "whirlpool", "dry hop"]
HOP_TIME_UNIT = {"boil": "min", "first wort": "min", "flameout": "min", "whirlpool": "min", "dry hop": "days"}

# How much of a full boil's utilization (Tinseth, at the same number of minutes) each use gets.
# Boil counts in full. First wort hops count 10% extra (first wort hopping is generally credited
# with a bit more bitterness than the same hops boiled for the same time). Flameout and whirlpool
# steeps and dry hops add no calculated bitterness. (The spreadsheet gave first wort the same
# utilization as a boil: that 10% is a difference from it.)
USE_UTILIZATION = {"boil": 1.0, "first wort": 1.1, "flameout": 0.0, "whirlpool": 0.0, "dry hop": 0.0}
BITTERING_USES = {use for use, factor in USE_UTILIZATION.items() if factor > 0}


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


@dataclass
class Grain:
    name: str
    lbs: float
    lovibond: float
    ppg: float


@dataclass
class Hop:
    name: str
    oz: float
    alpha_acid: float  # percent, e.g. 11.0
    minutes: float
    form: str = "pellet"
    use: str = "boil"


@dataclass
class Batch:
    pre_boil_gal: float = 6.5
    post_boil_gal: float = 5.5
    efficiency_pct: float = 65.0
    attenuation_pct: float = 75.0


@dataclass
class Mash:
    thickness_qt_per_lb: float = 1.25
    grain_temp_f: float = 68.0
    mash_temp_f: float = 152.0
    # Target temperatures for boiling-water infusion steps (e.g. mash-out).
    step_temps_f: list[float] = field(default_factory=list)
    boiling_water_temp_f: float = 210.0
    # The spreadsheet assumed the mash cools 3 °F before the first step.
    rest_temp_loss_f: float = 3.0
    grain_absorption_gal_per_lb: float = 0.125
    mash_tun_deadspace_gal: float = 0.0


# --------------------------------------------------------------------------
# Gravity, alcohol, color
# --------------------------------------------------------------------------


def max_points_per_gal(grains: list[Grain], pre_boil_gal: float) -> float:
    """Gravity points per gallon of pre-boil wort at 100% efficiency (M4)."""
    if pre_boil_gal <= 0:
        return 0.0
    return sum(g.ppg * g.lbs for g in grains) / pre_boil_gal


def pre_boil_gravity(grains: list[Grain], batch: Batch) -> float:
    """K13: 1 + (M4 * eff) / 1000."""
    pts = max_points_per_gal(grains, batch.pre_boil_gal)
    return 1 + pts * batch.efficiency_pct / 100 / 1000


def original_gravity(grains: list[Grain], batch: Batch) -> float:
    """K16: pre-boil points concentrated into the post-boil volume."""
    if batch.post_boil_gal <= 0:
        return 1.0
    pts = max_points_per_gal(grains, batch.pre_boil_gal)
    return 1 + pts * batch.efficiency_pct / 100 * batch.pre_boil_gal / batch.post_boil_gal / 1000


def final_gravity(og: float, attenuation_pct: float) -> float:
    """K19: apparent attenuation removes that share of the gravity points."""
    return og - attenuation_pct / 100 * (og - 1)


def abv(og: float, fg: float) -> float:
    """M7: the standard 131.25 approximation."""
    return 131.25 * (og - fg)


def abv_alternate(og: float, fg: float) -> float:
    """N7: the more accurate formula, better for strong beers."""
    return (76.08 * (og - fg) / (1.775 - og)) * (fg / 0.794)


def actual_efficiency(measured_pre_boil_sg: float, grains: list[Grain], pre_boil_gal: float) -> float:
    """O4: measured pre-boil points / maximum possible points, as a percent."""
    pts = max_points_per_gal(grains, pre_boil_gal)
    if pts <= 0:
        return 0.0
    return (measured_pre_boil_sg - 1) * 1000 / pts * 100


def mcu(grains: list[Grain], post_boil_gal: float) -> float:
    """Malt color units: lbs * °L / gallons (column G)."""
    if post_boil_gal <= 0:
        return 0.0
    return sum(g.lbs * g.lovibond for g in grains) / post_boil_gal


def srm_morey(mcu_value: float) -> float:
    """O7: Morey equation."""
    return 1.4922 * mcu_value**0.6859 if mcu_value > 0 else 0.0


def srm_color_name(srm: float, color_table: list[tuple[float, str]]) -> str:
    """P7: color_table rows are (upper SRM bound, name), sorted ascending.

    The bound is exclusive, matching the spreadsheet's MATCH(..., 1).
    """
    for upper, name in color_table:
        if srm < upper:
            return name
    return color_table[-1][1] if color_table else ""


# Display colors for SRM 1-40 (standard table used by brewing software).
_SRM_HEX = (
    "FFE699 FFD878 FFCA5A FFBF42 FBB123 F8A600 F39C00 EA8F00 E58500 DE7C00 "
    "D77200 CF6900 CB6200 C35900 BB5100 B54C00 B04500 A63E00 A13700 9B3200 "
    "952D00 8E2900 882300 821E00 7B1A00 771900 701400 6A0E00 660D00 5E0B00 "
    "5A0A02 600903 520907 4C0505 470606 440607 3F0708 3B0607 3A070B 36080A"
).split()


def srm_to_hex(srm: float) -> str:
    """Approximate display color for an SRM value (not in the spreadsheet)."""
    i = min(max(round(srm), 1), len(_SRM_HEX)) - 1
    return "#" + _SRM_HEX[i]


# --------------------------------------------------------------------------
# Bitterness (Tinseth)
# --------------------------------------------------------------------------


def boil_gravity_points(grains: list[Grain], batch: Batch) -> float:
    """The (gravity - 1) the spreadsheet uses in Tinseth's bigness factor.

    It spreads the pre-boil sugar over (post-boil gallons + 1), a rough
    average of the gravity during the boil. Kept as-is so IBUs match.
    """
    pts = max_points_per_gal(grains, batch.pre_boil_gal)
    return pts * batch.efficiency_pct / 100 * batch.pre_boil_gal / (batch.post_boil_gal + 1) / 1000


def tinseth_utilization(minutes: float, boil_gravity_minus_1: float, form: str = "pellet") -> float:
    """Column I: bigness factor * boil-time factor * hop form factor."""
    bigness = 1.65 * 0.000125**boil_gravity_minus_1
    time_factor = (1 - math.exp(-0.04 * max(minutes, 0))) / 4.15
    return bigness * time_factor * HOP_FORM_FACTOR.get(form.lower(), 1.0)


def hop_utilization(hop: Hop, grains: list[Grain], batch: Batch) -> float:
    """Tinseth utilization for this addition, scaled for how it is used (USE_UTILIZATION)."""
    factor = USE_UTILIZATION.get(hop.use, 0.0)
    if factor <= 0:
        return 0.0
    return factor * tinseth_utilization(hop.minutes, boil_gravity_points(grains, batch), hop.form)


def hop_ibu(hop: Hop, grains: list[Grain], batch: Batch) -> float:
    """Column J: util * oz * AA/100 * 7490 / gallons.

    FIX: spreadsheet rows 31-35 used `*75` instead of `/100*7490`, which
    would have inflated those additions' IBUs about 100x.
    """
    if batch.post_boil_gal <= 0:
        return 0.0
    return hop_utilization(hop, grains, batch) * hop.oz * hop.alpha_acid / 100 * 7490 / batch.post_boil_gal


def total_ibu(hops: list[Hop], grains: list[Grain], batch: Batch) -> float:
    return sum(hop_ibu(h, grains, batch) for h in hops)


# --------------------------------------------------------------------------
# Mash water
# --------------------------------------------------------------------------


def strike_water_qt(total_grain_lbs: float, mash: Mash) -> float:
    """M27: grain weight * mash thickness."""
    return total_grain_lbs * mash.thickness_qt_per_lb


def strike_water_temp(mash: Mash) -> float:
    """M26: Palmer's strike temp, Tw = (0.2 / r)(T2 - T1) + T2."""
    return 0.2 / mash.thickness_qt_per_lb * (mash.mash_temp_f - mash.grain_temp_f) + mash.mash_temp_f


@dataclass
class InfusionStep:
    target_temp_f: float
    start_temp_f: float
    boiling_water_qt: float
    total_mash_water_qt: float  # after this addition


def infusion_steps(total_grain_lbs: float, mash: Mash) -> list[InfusionStep]:
    """M29/M31/M33: boiling water for each step, Palmer's infusion equation.

    Wa = (T2 - T1)(0.2 G + Wm) / (Tw - T2)

    FIX: the spreadsheet divided by (Tw - previous temp) instead of
    (Tw - target temp), which under-dosed the water by about 30%. Its later
    steps also left out the water already added in earlier steps (Wm).
    Each step here starts `rest_temp_loss_f` below the previous target; the
    spreadsheet applied that 3 °F drop to the first step only.
    """
    steps: list[InfusionStep] = []
    water_qt = strike_water_qt(total_grain_lbs, mash)
    prev = mash.mash_temp_f
    tw = mash.boiling_water_temp_f
    for target in mash.step_temps_f:
        start = prev - mash.rest_temp_loss_f
        if target <= start or target >= tw:
            added = 0.0
        else:
            added = (target - start) * (0.2 * total_grain_lbs + water_qt) / (tw - target)
        water_qt += added
        steps.append(InfusionStep(target, start, added, water_qt))
        prev = target
    return steps


# Decoction mashing: a thick portion of the mash is pulled, boiled and returned to raise the whole mash.
DECOCTION_BOIL_TEMP_F = 212.0
GRAIN_DISPLACEMENT_QT_PER_LB = 0.32  # volume the grain takes up in the mash tun


@dataclass
class DecoctionStep:
    name: str
    target_temp_f: float
    minutes: float
    start_temp_f: float  # mash temperature just before the pull
    pull_fraction: float  # share of the mash (by volume) that is pulled and boiled
    pull_qt: float


@dataclass
class Decoction:
    strike_water_qt: float
    strike_water_temp_f: float
    mash_volume_qt: float  # water plus grain
    steps: list[DecoctionStep]
    sparge_water_gal: float


def decoction_schedule(total_grain_lbs: float, mash: Mash, steps: list[dict], pre_boil_gal: float) -> Decoction | None:
    """Strike water and the decoction pulls for a stepped mash.

    The first step is the dough-in: strike water is sized to land on its temperature. Every later step is reached
    by pulling a thick portion of the mash, boiling it and returning it. The thick portion has the same make-up as
    the whole mash, so a heat balance gives the share to pull: f = (target - start) / (boil - start). Each rest
    cools the mash by `rest_temp_loss_f` per 60 minutes before the next pull.
    """
    steps = [s for s in steps if s.get("temp_f") is not None]
    if not steps:
        return None
    first = replace(mash, mash_temp_f=float(steps[0]["temp_f"]), step_temps_f=[])
    strike_qt = strike_water_qt(total_grain_lbs, first)
    volume_qt = strike_qt + total_grain_lbs * GRAIN_DISPLACEMENT_QT_PER_LB
    out: list[DecoctionStep] = []
    prev_target = prev_minutes = 0.0
    for i, step in enumerate(steps):
        target = float(step["temp_f"])
        minutes = float(step.get("minutes") or 0)
        start = target if i == 0 else prev_target - mash.rest_temp_loss_f * prev_minutes / 60
        if i == 0 or target <= start or target >= DECOCTION_BOIL_TEMP_F:
            fraction = 0.0
        else:
            fraction = (target - start) / (DECOCTION_BOIL_TEMP_F - start)
        out.append(DecoctionStep(step.get("name") or "", target, minutes, start, fraction, fraction * volume_qt))
        prev_target, prev_minutes = target, minutes
    return Decoction(strike_qt, strike_water_temp(first), volume_qt, out, sparge_water_gal(total_grain_lbs, pre_boil_gal, first))


def sparge_water_gal(total_grain_lbs: float, pre_boil_gal: float, mash: Mash) -> float:
    """Water needed to reach the pre-boil volume after the mash.

    FIX: the spreadsheet used lbs of grain / 2 (O24), which is not tied to
    any volumes. This is a water balance: pre-boil volume plus water lost to
    grain absorption and mash-tun deadspace, minus water already in the mash.
    """
    mash_water_qt = strike_water_qt(total_grain_lbs, mash)
    steps = infusion_steps(total_grain_lbs, mash)
    if steps:
        mash_water_qt = steps[-1].total_mash_water_qt
    needed = pre_boil_gal + total_grain_lbs * mash.grain_absorption_gal_per_lb + mash.mash_tun_deadspace_gal
    return max(needed - mash_water_qt / 4, 0.0)


# --------------------------------------------------------------------------
# Style comparison
# --------------------------------------------------------------------------


@dataclass
class StyleRange:
    """A style's calculator ranges (None where the guidelines give none, e.g. "varies") and its BJCP text sections."""

    name: str
    abv: tuple[float, float] | None
    ibu: tuple[float, float] | None
    og: tuple[float, float] | None
    fg: tuple[float, float] | None
    srm: tuple[float, float] | None
    info: dict[str, str] = field(default_factory=dict)


def in_range(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]


# --------------------------------------------------------------------------
# Whole recipe
# --------------------------------------------------------------------------


@dataclass
class RecipeResult:
    total_grain_lbs: float
    max_points_per_gal: float
    pre_boil_gravity: float
    og: float
    fg: float
    abv: float
    abv_alternate: float
    mcu: float
    srm: float
    ibu: float
    hop_ibus: list[float]
    strike_water_qt: float
    strike_water_temp_f: float
    infusions: list[InfusionStep]
    sparge_water_gal: float


def calculate(grains: list[Grain], hops: list[Hop], batch: Batch, mash: Mash) -> RecipeResult:
    lbs = sum(g.lbs for g in grains)
    og = original_gravity(grains, batch)
    fg = final_gravity(og, batch.attenuation_pct)
    m = mcu(grains, batch.post_boil_gal)
    hop_ibus = [hop_ibu(h, grains, batch) for h in hops]
    return RecipeResult(
        total_grain_lbs=lbs,
        max_points_per_gal=max_points_per_gal(grains, batch.pre_boil_gal),
        pre_boil_gravity=pre_boil_gravity(grains, batch),
        og=og,
        fg=fg,
        abv=abv(og, fg),
        abv_alternate=abv_alternate(og, fg),
        mcu=m,
        srm=srm_morey(m),
        ibu=sum(hop_ibus),
        hop_ibus=hop_ibus,
        strike_water_qt=strike_water_qt(lbs, mash),
        strike_water_temp_f=strike_water_temp(mash),
        infusions=infusion_steps(lbs, mash),
        sparge_water_gal=sparge_water_gal(lbs, batch.pre_boil_gal, mash),
    )


# --------------------------------------------------------------------------
# Carbonation
# --------------------------------------------------------------------------

# One "volume" of CO2 is a litre of CO2 gas (at 0 C, 1 atm) dissolved per litre of beer.
CO2_G_PER_L_PER_VOLUME = 1.977
LITRES_PER_GAL = 3.785411784

# Grams of CO2 made per gram of priming sugar, from the chemistry: 1 glucose -> 2 CO2, 1 sucrose -> 4 CO2.
# Corn sugar is dextrose monohydrate (180.16 / 198.17 = 90.9% glucose). BYO's priming chart (volumes per ounce in
# 5 gal) agrees with these three to two decimals. Malt extract is not from a source: it assumes 95% solids of
# which 75% ferment (as maltose, 4 CO2 per 342 g), so treat it as approximate.
PRIMING_SUGARS = {
    "Corn sugar (dextrose monohydrate)": 2 * 44.01 / 198.17,
    "Table sugar (sucrose)": 4 * 44.01 / 342.30,
    "Dextrose (anhydrous)": 2 * 44.01 / 180.16,
    "Dried malt extract (approximate)": 0.95 * 0.75 * 4 * 44.01 / 342.30,
}
DEFAULT_PRIMING_SUGAR = "Corn sugar (dextrose monohydrate)"

# Usual carbonation ranges in volumes of CO2 (BYO's carbonation chart).
CARBONATION_STYLES = [
    ("British ales", 1.5, 2.2),
    ("American ales", 2.2, 3.0),
    ("European lagers", 2.4, 2.6),
    ("American lagers", 2.5, 2.8),
    ("Belgian ales", 2.0, 4.5),
    ("German wheat beers (Weizen)", 2.8, 5.1),
]


def residual_co2_volumes(beer_temp_f: float) -> float:
    """CO2 already dissolved in finished beer, from the warmest temperature it has been at since fermenting."""
    return max(0.0, 3.0378 - 0.050062 * beer_temp_f + 0.00026555 * beer_temp_f**2)


def priming_sugar_g(volume_gal: float, beer_temp_f: float, target_volumes: float, sugar: str = DEFAULT_PRIMING_SUGAR) -> float:
    """Grams of priming sugar to bottle `volume_gal` of beer up to `target_volumes` of CO2."""
    needed = max(0.0, target_volumes - residual_co2_volumes(beer_temp_f))
    co2_g = needed * volume_gal * LITRES_PER_GAL * CO2_G_PER_L_PER_VOLUME
    return co2_g / PRIMING_SUGARS[sugar]


def keg_psi(beer_temp_f: float, target_volumes: float) -> float:
    """Regulator (gauge) pressure at which beer at `beer_temp_f` settles at `target_volumes` of CO2.

    Solves V = (P + 14.695) * (0.01821 + 0.09011 * exp(-(T - 32) / 43.11)) - 0.003342 for P
    (the CO2 solubility equation in Wetnewf's "CO2 Volumes" article, as used by brew_tools)."""
    solubility = 0.01821 + 0.09011 * math.exp(-(beer_temp_f - 32) / 43.11)
    return max(0.0, (target_volumes + 0.003342) / solubility - 14.695)
