"""
Curated seed list of US early-stage funds that skew consumer / B2C, with a
marketplace tilt where known. These are high-precision starting points; the
pipeline still verifies every one against the live web, estimates fund size,
and classifies it, so nothing here is trusted blindly.

`domain` is filled only where we are fairly confident; a blank domain is fine,
discovery resolves it via search. Keep this list names-and-domains only, no
claims, so verification stays the source of truth.
"""

from __future__ import annotations

# (name, domain_or_empty, hint)  hint is a loose tag to help the classifier,
# never treated as ground truth.
SEED_FUNDS: list[tuple[str, str, str]] = [
    ("Hustle Fund", "hustlefund.vc", "pre-seed consumer-friendly"),
    ("Weekend Fund", "weekend.fund", "consumer"),
    ("Chapter One", "chapterone.com", "consumer marketplace"),
    ("Maple VC", "maple.vc", "marketplaces"),
    ("Supernode Ventures", "supernode.vc", "marketplaces network effects"),
    ("Long Journey Ventures", "longjourney.ventures", "consumer"),
    ("Day One Ventures", "dayoneventures.com", "consumer"),
    ("Wischoff Ventures", "wischoff.com", "consumer fintech"),
    ("Animal Capital", "animalcapital.co", "gen z consumer creator"),
    ("Cake Ventures", "cakeventures.com", "consumer demographic shifts"),
    ("Moxxie Ventures", "moxxie.vc", "consumer tech"),
    ("Halogen Ventures", "halogenvc.com", "female-founded consumer"),
    ("BBG Ventures", "bbgventures.com", "consumer women-led"),
    ("Coefficient Capital", "coefficientcap.com", "consumer CPG"),
    ("Selva Ventures", "selva.vc", "consumer health"),
    ("Willow Growth", "willowgrowthpartners.com", "consumer"),
    ("Female Founders Fund", "femalefoundersfund.com", "consumer"),
    ("Cassius", "", "consumer marketplace"),
    ("Courtside Ventures", "courtsidevc.com", "sports media marketplaces"),
    ("Starting Line", "startingline.vc", "consumer"),
    ("Twelve Below", "twelvebelow.com", "consumer marketplace seed"),
    ("Notation Capital", "notation.vc", "pre-seed nyc"),
    ("Gutter Capital", "gutter.vc", "pre-seed"),
    ("Bread and Butter Ventures", "breadandbutter.vc", "marketplace food"),
    ("Alpaca VC", "alpaca.vc", "proptech consumer marketplaces"),
    ("Interplay", "interplay.vc", "marketplaces fintech"),
    ("Behind Genius Ventures", "behindgenius.vc", "consumer creator"),
    ("Type One Ventures", "typeone.vc", "deep tech consumer"),
    ("XFactor Ventures", "xfactor.ventures", "female founders pre-seed"),
    ("Vitalize Ventures", "vitalize.vc", "consumer future of work"),
    ("Hannah Grey VC", "hannahgrey.com", "consumer"),
    ("Gingerbread Capital", "gingerbreadcap.com", "consumer women-led"),
    ("Graham & Walker", "grahamwalker.com", "consumer"),
    ("Slow Ventures", "slow.co", "consumer creator"),
    ("Not Boring Capital", "notboring.co", "consumer generalist"),
    ("Liquid 2 Ventures", "liquid2.vc", "generalist consumer"),
    ("Browder Capital", "", "consumer"),
    ("Sweater Ventures", "sweaterventures.com", "consumer"),
    ("VU Venture Partners", "vuventures.com", "consumer marketplaces"),
    ("645 Ventures", "645ventures.com", "consumer"),
    ("Corazon Capital", "corazon.co", "consumer marketplaces"),
    ("Bee Partners", "beepartners.vc", "pre-seed"),
    ("The Fund", "thefund.vc", "consumer network"),
    ("Company Ventures", "company.co", "consumer"),
    ("Great Oaks Venture Capital", "greatoaksvc.com", "consumer"),
    ("Patron", "patron.vc", "consumer gaming community"),
    ("Konvoy", "konvoy.vc", "gaming consumer"),
    ("Offline Ventures", "", "consumer cpg"),
    ("Coalition Operators", "coalitionoperators.com", "consumer"),
    ("Outsiders Fund", "outsiders.fund", "consumer brands"),
    ("Cake Ventures", "cakeventures.com", "consumer"),
    ("Stitch Ventures", "", "consumer"),
    ("Burst Capital", "", "consumer"),
    ("Aglae", "", "consumer"),
    ("Imaginary Ventures", "imaginary.co", "consumer retail"),
    ("Forerunner Ventures", "forerunnerventures.com", "consumer"),
    ("Lerer Hippeau", "lererhippeau.com", "consumer"),
    ("Collaborative Fund", "collabfund.com", "consumer"),
    ("Maveron", "maveron.com", "consumer only"),
    ("FJ Labs", "fjlabs.com", "marketplaces"),
    ("Version One Ventures", "versionone.vc", "marketplaces network effects"),
    ("NFX", "nfx.com", "marketplaces network effects"),
    ("Bullish", "bullish.co", "consumer brands"),
    ("TMV", "tmv.vc", "consumer"),
    ("Coral Capital", "", "consumer"),
    ("Bolster", "", "consumer marketplace"),
    ("Riverpark Ventures", "", "consumer marketplaces"),
    ("Ulu Ventures", "uluventures.com", "consumer"),
    ("Springbank Collective", "springbank.vc", "consumer family"),
    ("Cake", "", "consumer"),
    ("Behind Genius", "behindgenius.vc", "consumer creator"),
]


def seed_names() -> list[dict]:
    """Deduped seed candidates as {firm, website, hint, source}."""
    seen = set()
    out = []
    for name, domain, hint in SEED_FUNDS:
        key = name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "firm": name.strip(),
                "website": f"https://{domain}" if domain else "",
                "hint": hint,
                "source": "curated_seed",
            }
        )
    return out
