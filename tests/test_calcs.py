"""Check the calculator against the values BrewingCalculator_JKH.xlsx produced
for the American IPA recipe that was entered in it (data/example_recipe.json).
"""

import json
from pathlib import Path

import pytest

from brewcalc import calcs, recipe, reference

_REAL_GRAINS = reference.grains  # the autouse fixture below swaps reference.grains out
EXAMPLE = json.loads((Path(__file__).resolve().parent.parent / "data" / "example_recipe.json").read_text())
# The spreadsheet used 11% alpha acid for Citra. Pin it so these tests check the formulas,
# not whatever the hop reference file currently says.
for _hop in EXAMPLE["hops"]:
    _hop["alpha_acid"] = 11.0
# The spreadsheet had 1 gal between pre-boil and the end of the boil and no trub allowance. Pin that too
# (the example file now splits it into 0.5 boil-off + 0.5 trub, which moves OG, IBU and color).
EXAMPLE["batch"].update(boil_off_gal=1.0, trub_loss_gal=0.0)
# The spreadsheet had 12 lb of base malt; the example file now has 14. Pin 12 so the spreadsheet values still apply.
assert EXAMPLE["grains"][0]["name"] == "Brewers Malt, Briess"
EXAMPLE["grains"][0]["lbs"] = 12.0


@pytest.fixture(autouse=True)
def spreadsheet_grains(monkeypatch):
    """Pin the three example grains to the values the spreadsheet used, so these tests check the formulas rather
    than the fermentables reference file (which now lists real maltster products)."""
    real = _REAL_GRAINS()
    pinned = {
        "Brewers Malt, Briess": (1.8, 37.5),
        "Caramel Malt 20L, Briess": (20.0, 35.0),
        "Château Biscuit, Castle Malting": (24.0, 35.0),
    }
    out = dict(real)
    for name, (lov, ppg) in pinned.items():
        out[name] = {**real[name], "lovibond": lov, "ppg": ppg}
    monkeypatch.setattr(reference, "grains", lambda: out)


@pytest.fixture
def result():
    # The spreadsheet's San Diego Super Yeast attenuation was 80%. Pin it so these checks test the
    # formulas, not the yeast reference file (test_attenuation_comes_from_yeast tests the lookup).
    return recipe.calculate({**EXAMPLE, "attenuation_pct": 80.0})


# Values cached in the spreadsheet cells (cell reference in the comment).
@pytest.mark.parametrize(
    "attr, expected",
    [
        ("max_points_per_gal", 77.307692307692307),  # M4
        ("pre_boil_gravity", 1.0502499999999999),  # K13
        ("og", 1.0593863636363636),  # K16
        ("fg", 1.0118772727272727),  # K19
        ("abv", 6.235568181818187),  # M7
        ("abv_alternate", 6.4368880447627772),  # N7
        ("srm", 7.2938875999198522),  # O7
        # M10, plus the 10% first-wort bonus on the first hop line (a deliberate difference from the spreadsheet)
        ("ibu", 63.813700186608017 + 0.1 * 22.966896237528832),
        ("total_grain_lbs", 13.5),  # M22
        ("strike_water_temp_f", 165.44),  # M26
        ("strike_water_qt", 16.875),  # M27
    ],
)
def test_matches_spreadsheet(result, attr, expected):
    assert getattr(result, attr) == pytest.approx(expected, rel=1e-12)


def test_hop_ibus_match_spreadsheet(result):
    # J22..J26: 20 min (first wort), 40 min, 5 min, flameout, dry hop
    # The first line is a first wort addition: the spreadsheet's 22.967 plus the 10% first-wort bonus.
    assert result.hop_ibus == pytest.approx([1.1 * 22.966896237528832, 33.286587932925386, 7.5602160161537988, 0, 0])


def test_attenuation_comes_from_yeast():
    assert recipe.attenuation(EXAMPLE) == reference.yeasts()["San Diego Super Yeast"]["attenuation"]  # C39


def test_color_name(result):
    assert calcs.srm_color_name(result.srm, reference.srm_colors()) == "Light Amber"  # P7
    # The bound is exclusive, as in the spreadsheet's MATCH(..., 1).
    assert calcs.srm_color_name(7.0, reference.srm_colors()) == "Light Amber"
    assert calcs.srm_color_name(6.99, reference.srm_colors()) == "Gold"


def test_bjcp_styles_load_with_sections():
    styles = reference.styles()
    assert len(styles) == 123
    ipa = styles["21A. American IPA"]
    assert "hop" in ipa.info["Overall Impression"].lower()
    assert ipa.info["Characteristic Ingredients"]
    assert set(ipa.info) >= {"Aroma", "Appearance", "Flavor", "Mouthfeel", "Vital Statistics", "Commercial Examples", "Tags"}
    # Styles whose vitals "vary" have no ranges.
    assert styles["34C. Experimental Beer"].og is None
    assert styles["21B. Specialty IPA: Black IPA"].srm == (25, 40)


def test_find_style_accepts_old_and_unnumbered_names():
    assert reference.find_style("21A. American IPA").name == "21A. American IPA"
    assert reference.find_style("American IPA").name == "21A. American IPA"
    assert reference.find_style("Light American Lager").name == "1A. American Light Lager"
    assert reference.find_style("Kolsch").name == "5B. Kölsch"
    assert reference.find_style("") is None and reference.find_style("Nonsense") is None


def test_style_ranges(result):
    style = reference.styles()["21A. American IPA"]  # N14:R14
    assert (style.abv, style.ibu, style.og, style.fg, style.srm) == (
        (5.5, 7.5),
        (40, 70),
        (1.056, 1.07),
        (1.008, 1.014),
        (6, 14),
    )
    # N16:R16 all YES
    assert all(
        calcs.in_range(v, r)
        for v, r in [
            (result.abv, style.abv),
            (result.ibu, style.ibu),
            (result.og, style.og),
            (result.fg, style.fg),
            (result.srm, style.srm),
        ]
    )


def test_actual_efficiency():
    grains, _, batch, _ = recipe.to_inputs(EXAMPLE)
    assert calcs.actual_efficiency(1.05025, grains, batch.pre_boil_gal) == pytest.approx(65)


# --- Fixes to the spreadsheet ---------------------------------------------


def test_infusion_uses_target_temp_in_divisor(result):
    # Palmer: Wa = (T2 - T1)(0.2 G + Wm) / (Tw - T2)
    # (170 - 149)(0.2 * 13.5 + 16.875) / (210 - 170) = 10.277 qt.
    # The spreadsheet (M29) divided by 210 - 152 and gave 7.0875 qt.
    (step,) = result.infusions
    assert step.start_temp_f == 149
    assert step.boiling_water_qt == pytest.approx(21 * 19.575 / 40)


def test_infusion_heat_balance():
    """The mixed temperature should land on each step's target."""
    mash = calcs.Mash(step_temps_f=[158, 170])
    lbs = 13.5
    temp = mash.mash_temp_f
    water = calcs.strike_water_qt(lbs, mash)
    for step in calcs.infusion_steps(lbs, mash):
        start = temp - mash.rest_temp_loss_f
        mixed = ((0.2 * lbs + water) * start + step.boiling_water_qt * mash.boiling_water_temp_f) / (
            0.2 * lbs + water + step.boiling_water_qt
        )
        assert mixed == pytest.approx(step.target_temp_f)
        water += step.boiling_water_qt
        temp = step.target_temp_f
    assert water == pytest.approx(step.total_mash_water_qt)


def test_infusion_below_start_temp_adds_nothing():
    (step,) = calcs.infusion_steps(10, calcs.Mash(mash_temp_f=152, step_temps_f=[148]))
    assert step.boiling_water_qt == 0


def test_rows_31_to_35_ibu_bug_is_fixed():
    # The spreadsheet's rows 31-35 used *75 instead of /100*7490.
    grains, _, batch, _ = recipe.to_inputs(EXAMPLE)
    hop = calcs.Hop("Citra", oz=1, alpha_acid=11, minutes=20)
    assert calcs.hop_ibu(hop, grains, batch) == pytest.approx(22.966896237528832)


def test_non_bittering_uses_give_no_ibu():
    grains, _, batch, _ = recipe.to_inputs(EXAMPLE)
    for use in ("flameout", "whirlpool", "dry hop"):
        assert calcs.hop_ibu(calcs.Hop("Citra", 1, 11, 60, use=use), grains, batch) == 0


def test_sparge_water_balance(result):
    # 6.5 gal pre-boil + 13.5 lb * 0.125 gal/lb absorbed - mash water
    mash_gal = result.infusions[-1].total_mash_water_qt / 4
    assert result.sparge_water_gal == pytest.approx(6.5 + 13.5 * 0.125 - mash_gal)


def test_alpha_acid_override():
    r = json.loads(json.dumps(EXAMPLE))
    r["hops"][1]["alpha_acid"] = 22  # double the reference 11%
    assert recipe.calculate(r).hop_ibus[1] == pytest.approx(2 * 33.286587932925386)


def test_empty_recipe_does_not_crash():
    res = recipe.calculate(recipe.DEFAULT_RECIPE)
    assert (res.og, res.ibu, res.srm) == (1.0, 0.0, 0.0)


def test_hop_use_scales_bitterness():
    grains = [calcs.Grain("pale", 10, 2, 36)]
    batch = calcs.Batch()

    def ibu(use, time):
        return calcs.hop_ibu(calcs.Hop("h", 1, 10, time, "pellet", use), grains, batch)

    boil = ibu("boil", 15)
    assert boil > 0
    assert ibu("first wort", 15) == pytest.approx(1.1 * boil)  # first wort gets 10% extra
    for use in ("flameout", "whirlpool", "dry hop"):
        assert ibu(use, 15) == 0


def test_every_use_has_a_time_unit():
    assert set(calcs.HOP_TIME_UNIT) == set(calcs.HOP_USES) == set(calcs.USE_UTILIZATION)
    assert calcs.HOP_TIME_UNIT["dry hop"] == "days" and calcs.HOP_TIME_UNIT["boil"] == "min"


def test_zero_attenuation_override_means_use_the_yeast():
    assert recipe.attenuation({**EXAMPLE, "attenuation_pct": 0}) == reference.yeasts()["San Diego Super Yeast"]["attenuation"]


def test_boil_off_and_trub_loss_split():
    b = recipe.normalize({})["batch"]
    assert (b["boil_off_gal"], b["trub_loss_gal"]) == (0.5, 0.5)
    assert b["pre_boil_gal"] == b["post_boil_gal"] + 1.0
    # A recipe from before the split: the whole difference is boil-off.
    old = recipe.normalize({"batch": {"pre_boil_gal": 7.0, "post_boil_gal": 5.0, "efficiency_pct": 70}})["batch"]
    assert (old["boil_off_gal"], old["trub_loss_gal"]) == (2.0, 0.0)
    # Volumes edited elsewhere (Streamlit): trub is kept, boil-off takes the difference.
    edited = recipe.normalize({"batch": {"pre_boil_gal": 8.0, "post_boil_gal": 5.0, "boil_off_gal": 0.5, "trub_loss_gal": 0.5}})["batch"]
    assert (edited["boil_off_gal"], edited["trub_loss_gal"]) == (2.5, 0.5)


def test_og_is_worked_out_at_target_volume_plus_trub():
    # Same sugar in (target + trub) gallons: more trub means a lower OG; boil-off only changes the pre-boil volume.
    def og(**batch):
        r = json.loads(json.dumps(EXAMPLE))
        r["batch"].update(batch)
        r["batch"]["pre_boil_gal"] = r["batch"]["post_boil_gal"] + r["batch"]["boil_off_gal"] + r["batch"]["trub_loss_gal"]
        return recipe.calculate(r)

    base = og(boil_off_gal=1.0, trub_loss_gal=0.0)  # the example before the split: 5.5 gal at the end of the boil
    assert base.og == pytest.approx(1.0593863636363636)
    with_trub = og(boil_off_gal=1.0, trub_loss_gal=0.5)
    assert with_trub.og == pytest.approx(1 + 0.0593863636363636 * 5.5 / 6.0)
    assert og(boil_off_gal=2.0, trub_loss_gal=0.0).og == pytest.approx(base.og)


def test_decoction_schedule():
    mash = calcs.Mash(thickness_qt_per_lb=1.25, rest_temp_loss_f=3.0)
    steps = [
        {"name": "Protein", "temp_f": 131, "minutes": 20},
        {"name": "Sacch", "temp_f": 152, "minutes": 60},
        {"name": "Mash out", "temp_f": 170, "minutes": 10},
    ]
    d = calcs.decoction_schedule(13.5, mash, steps, 6.5)
    assert d.strike_water_qt == pytest.approx(16.875)
    assert d.strike_water_temp_f == pytest.approx(calcs.strike_water_temp(calcs.Mash(mash_temp_f=131)))
    assert d.mash_volume_qt == pytest.approx(16.875 + 13.5 * 0.32)
    first, sacch, out = d.steps
    assert (first.pull_fraction, first.pull_qt) == (0, 0)  # the dough-in step needs no pull
    # 20 min rest loses 1 F: 130 F before the pull; f = (152 - 130) / (212 - 130)
    assert sacch.start_temp_f == pytest.approx(130)
    assert sacch.pull_fraction == pytest.approx(22 / 82)
    assert sacch.pull_qt == pytest.approx(22 / 82 * d.mash_volume_qt)
    # 60 min rest loses 3 F: 149 F before the pull
    assert out.pull_fraction == pytest.approx(21 / 63)
    # heat balance: returning the boiled share lands on the target
    f = sacch.pull_fraction
    assert (1 - f) * sacch.start_temp_f + f * 212 == pytest.approx(152)
    # no infusion water, so sparge = pre-boil + absorption - strike water
    assert d.sparge_water_gal == pytest.approx(6.5 + 13.5 * 0.125 - 16.875 / 4)


def test_decoction_needs_a_temperature():
    assert calcs.decoction_schedule(10, calcs.Mash(), [], 6.5) is None
    assert calcs.decoction_schedule(10, calcs.Mash(), [{"name": "x", "temp_f": None}], 6.5) is None


def test_a_step_that_is_not_higher_needs_no_pull():
    d = calcs.decoction_schedule(10, calcs.Mash(), [{"temp_f": 152, "minutes": 60}, {"temp_f": 140, "minutes": 10}], 6.5)
    assert d.steps[1].pull_fraction == 0


def test_fermentables_have_category_and_type():
    grains = reference.grains()
    assert all(g["category"] and g["type"] for g in grains.values())
    assert all(g["producer"] for g in grains.values() if g["category"] in ("Grain", "Extract"))
    assert {g["category"] for g in grains.values()} <= {"Grain", "Extract", "Sugar", "Fruit", "Other"}
    assert (grains["Pilsen Malt, Briess"]["category"], grains["Pilsen Malt, Briess"]["type"]) == ("Grain", "Base malt")
    assert grains["Caramel Malt 60L, Briess"]["type"] == "Crystal malt" and grains["Carafa Type 2, Weyermann"]["type"] == "Roasted malt"
    assert grains["CBW Golden Light DME, Briess"]["category"] == "Extract"
    assert {"Vienna Malt, Crisp", "Vienna Malt, Simpsons", "Vienna Malt, Weyermann"} <= set(grains)


def test_comprehensive_hop_list_parses():
    import csv

    with (reference.DATA_DIR / "hops_comprehensive.csv").open(newline="", encoding="utf-8") as f:
        rows = {r["name"]: r for r in csv.DictReader(f)}
    assert len(rows) == 153  # 68 HGA 2020 + 2 HGA 2011-only + 17 NZ + 34 UK + 32 BarthHaas (Germany, Czech, Slovenia, France, Australia, Talus)
    assert rows["Citra"]["alpha_range"] == "11–13" and float(rows["Citra"]["alpha_acid"]) == 12.0
    assert rows["Summit"]["alpha_range"] == "15–18"
    assert rows["Mosaic"]["alpha_range"] == "11.5–13.5" and "Pear" in rows["Mosaic"]["aroma"]
    assert rows["Cascade"]["substitutions"]  # 2011 manual details are kept for varieties in both
    assert rows["Tillicum"]["alpha_range"] == "12–14.5"
    assert rows["Nelson Sauvin"]["origin"] == "New Zealand" and float(rows["Nelson Sauvin"]["alpha_acid"]) == 11.5
    assert float(rows["Motueka"]["alpha_acid"]) == 7.75
    # US and UK versions of the same hop sit side by side; the original country's one has the plain name.
    assert rows["Cascade"]["origin"] == "USA" and rows["Cascade (UK)"]["origin"] == "UK"
    assert rows["Fuggle"]["origin"] == "UK" and rows["Fuggle (US)"]["origin"] == "USA"
    assert rows["First Gold"]["origin"] == "UK" and rows["First Gold (US)"]["origin"] == "USA"
    assert rows["Perle"]["origin"] == "Germany" and rows["Perle (US)"]["origin"] == "USA"
    assert rows["Saaz"]["origin"] == "Czech Republic" and rows["Galaxy"]["alpha_range"] == "11–18.5"
    assert "BarthHaas" in rows["Galaxy"]["source"]
    assert float(rows["East Kent Goldings"]["alpha_acid"]) == 5.0


def test_grain_with_producer_is_keyed_as_name_comma_producer(monkeypatch):
    rows = [
        {"name": "Pilsen Malt", "producer": "Briess", "lovibond": "1.5", "ppg": "37"},
        {"name": "Pilsen Malt", "producer": "Weyermann", "lovibond": "1.7", "ppg": "37"},
        {"name": "Honey", "producer": "", "lovibond": "1", "ppg": "35"},
    ]
    monkeypatch.setattr(reference, "_read", lambda name: [dict(r) for r in rows])
    _REAL_GRAINS.cache_clear()
    try:
        g = _REAL_GRAINS()
        assert set(g) == {"Pilsen Malt, Briess", "Pilsen Malt, Weyermann", "Honey"}
        assert g["Pilsen Malt, Briess"]["item"] == "Pilsen Malt" and g["Pilsen Malt, Briess"]["producer"] == "Briess"
    finally:
        _REAL_GRAINS.cache_clear()


def test_sugar_ppg_is_calculated_from_composition():
    g = _REAL_GRAINS()
    assert g["Dextrose (corn sugar)"]["ppg"] == pytest.approx(42.0, abs=0.1)
    assert g["Table Sugar (sucrose)"]["ppg"] == pytest.approx(46.2)
    assert g["Belgian Candi Sugar (clear)"]["ppg"] > g["Belgian Candi Syrup D-90 (dark), Candi Syrup Inc"]["ppg"]


def test_fruit_ppg_is_calculated_from_brix():
    g = reference.grains()
    assert g["Cranberry"]["category"] == "Fruit"
    assert g["Cherry, Sweet"]["ppg"] == pytest.approx(46.2 * 0.20, abs=0.05)
    assert g["Raspberry Puree (aseptic seedless), Oregon Fruit"]["ppg"] == pytest.approx(46.2 * 0.11, abs=0.05)


def test_recipe_has_free_text_additions_that_do_not_change_the_numbers():
    from brewcalc import recipe as rcp

    base = rcp.normalize(json.loads(Path("data/example_recipe.json").read_text()))
    assert base["additions"] == []
    with_add = {**base, "additions": [{"name": "Whirlfloc", "amount": "1", "unit": "tablet", "notes": "last 10 min"}]}
    a, b = rcp.calculate(base), rcp.calculate(rcp.normalize(with_add))
    assert (a.og, a.srm, a.ibu) == (b.og, b.srm, b.ibu)


# --- carbonation -------------------------------------------------------------


def test_residual_co2_matches_the_byo_example():
    # BYO's chart gives 0.850 volumes for beer held at 68 F.
    assert calcs.residual_co2_volumes(68) == pytest.approx(0.85, abs=0.02)
    assert calcs.residual_co2_volumes(50) > calcs.residual_co2_volumes(68) > calcs.residual_co2_volumes(75)


def test_priming_sugar_agrees_with_the_byo_chart():
    # BYO: 1 oz (28.3 g) of anhydrous glucose / glucose monohydrate / sucrose in 5 gal adds 0.37 / 0.34 / 0.39 volumes.
    oz = 28.35
    for sugar, volumes in [("Dextrose (anhydrous)", 0.37), ("Corn sugar (dextrose monohydrate)", 0.34), ("Table sugar (sucrose)", 0.39)]:
        added = oz * calcs.PRIMING_SUGARS[sugar] / (5 * calcs.LITRES_PER_GAL * calcs.CO2_G_PER_L_PER_VOLUME)
        assert added == pytest.approx(volumes, abs=0.006)


def test_priming_sugar_for_a_5_gallon_batch():
    # BYO's worked example: 2.4 volumes at 68 F needs about 128 g of glucose monohydrate in 5 gal.
    grams = calcs.priming_sugar_g(5, 68, 2.4)
    assert 125 < grams < 135
    assert calcs.priming_sugar_g(5, 68, 2.4, "Table sugar (sucrose)") < grams
    assert calcs.priming_sugar_g(5, 68, 0.5) == 0.0  # already has more CO2 than that from fermentation
    assert calcs.priming_sugar_g(10, 68, 2.4) == pytest.approx(2 * grams)


def test_keg_pressure():
    # The usual force-carbonation chart: about 11-12 psi for 2.5 volumes at 38 F; more when warmer or fizzier.
    assert calcs.keg_psi(38, 2.5) == pytest.approx(11.2, abs=0.4)
    assert calcs.keg_psi(45, 2.5) > calcs.keg_psi(38, 2.5) > calcs.keg_psi(34, 2.5)
    assert calcs.keg_psi(38, 3.0) > calcs.keg_psi(38, 2.5)
    assert calcs.keg_psi(38, 0.1) == 0.0
