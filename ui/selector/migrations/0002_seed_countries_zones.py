from django.db import migrations


def seed(apps, schema_editor):
    Country = apps.get_model("selector", "Country")
    Zone = apps.get_model("selector", "Zone")

    # Name -> ISO3 mapping for the GeoJSON map dataset (feature.id).
    # Kept explicit to avoid ambiguity (e.g., "Macedonia" vs "North Macedonia").
    name_to_iso3 = {
        "Albania": "ALB",
        "Austria": "AUT",
        "Bosnia and Herzegovina": "BIH",
        "Belgium": "BEL",
        "Bulgaria": "BGR",
        "Switzerland": "CHE",
        "Cyprus": "CYP",
        "Czech Republic": "CZE",
        "Germany": "DEU",
        "Denmark": "DNK",
        "Algeria": "DZA",
        "Estonia": "EST",
        "Egypt": "EGY",
        "Spain": "ESP",
        "Finland": "FIN",
        "France": "FRA",
        "Greece": "GRC",
        "Croatia": "HRV",
        "Hungary": "HUN",
        "Ireland": "IRL",
        "Israel": "ISR",
        "Iceland": "ISL",
        "Italy": "ITA",
        "Lithuania": "LTU",
        "Luxembourg": "LUX",
        "Latvia": "LVA",
        "Libya": "LBY",
        "Morocco": "MAR",
        "Moldova": "MDA",
        "Montenegro": "MNE",
        "Macedonia": "MKD",
        "Malta": "MLT",
        "Netherlands": "NLD",
        "Norway": "NOR",
        "Poland": "POL",
        "Palestine": "PSE",
        "Portugal": "PRT",
        "Romania": "ROU",
        "Republic of Serbia": "SRB",
        "Sweden": "SWE",
        "Slovenia": "SVN",
        "Slovakia": "SVK",
        "Tunisia": "TUN",
        "Turkey": "TUR",
        "Ukraine": "UKR",
        "United Kingdom": "GBR",
        "Belarus": "BLR",
    }

    # (zone_code, country_name)
    zone_rows = [
        ("AL00", "Albania"),
        ("AT00", "Austria"),
        ("BA00", "Bosnia and Herzegovina"),
        ("BE00", "Belgium"),
        ("BG00", "Bulgaria"),
        ("CH00", "Switzerland"),
        ("CY00", "Cyprus"),
        ("CZ00", "Czech Republic"),
        ("DE00", "Germany"),
        ("DEKF", "Germany"),
        ("DKE1", "Denmark"),
        ("DKKF", "Denmark"),
        ("DKW1", "Denmark"),
        ("DZ00", "Algeria"),
        ("EE00", "Estonia"),
        ("EG00", "Egypt"),
        ("ES00", "Spain"),
        ("FI00", "Finland"),
        ("FR00", "France"),
        ("FR15", "France"),
        ("GR00", "Greece"),
        ("GR03", "Greece"),
        ("HR00", "Croatia"),
        ("HU00", "Hungary"),
        ("IE00", "Ireland"),
        ("IL00", "Israel"),
        ("IS00", "Iceland"),
        ("ITCA", "Italy"),
        ("ITCN", "Italy"),
        ("ITCO", "Italy"),
        ("ITCS", "Italy"),
        ("ITN1", "Italy"),
        ("ITS1", "Italy"),
        ("ITSA", "Italy"),
        ("ITSI", "Italy"),
        ("ITVI", "Italy"),
        ("LT00", "Lithuania"),
        ("LUB1", "Luxembourg"),
        ("LUF1", "Luxembourg"),
        ("LUG1", "Luxembourg"),
        ("LUV1", "Luxembourg"),
        ("LV00", "Latvia"),
        ("LY00", "Libya"),
        ("MA00", "Morocco"),
        ("MD00", "Moldova"),
        ("ME00", "Montenegro"),
        ("MK00", "Macedonia"),
        ("MT00", "Malta"),
        ("NL00", "Netherlands"),
        ("NOM1", "Norway"),
        ("NON1", "Norway"),
        ("NOS0", "Norway"),
        ("PL00", "Poland"),
        ("PL00E", "Poland"),
        ("PL00I", "Poland"),
        ("PS00", "Palestine"),
        ("PT00", "Portugal"),
        ("RO00", "Romania"),
        ("RS00", "Republic of Serbia"),
        ("SE01", "Sweden"),
        ("SE02", "Sweden"),
        ("SE03", "Sweden"),
        ("SE04", "Sweden"),
        ("SI00", "Slovenia"),
        ("SK00", "Slovakia"),
        ("TN00", "Tunisia"),
        ("TR00", "Turkey"),
        ("UA00", "Ukraine"),
        ("UA01", "Ukraine"),
        ("UK00", "United Kingdom"),
        ("UKNI", "United Kingdom"),
        ("DKBH", "Denmark"),
        ("DKNS", "Denmark"),
        ("BEOF", "Belgium"),
        ("NLLL", "Netherlands"),
        ("NL6H", "Netherlands"),
        ("BY00", "Belarus"),
    ]

    # Create / upsert countries, then zones.
    countries_by_name = {}
    for _, cname in zone_rows:
        if cname in countries_by_name:
            continue
        iso3 = name_to_iso3.get(cname)
        if not iso3:
            # Skip unknown mapping rather than failing migrations.
            continue
        country, _ = Country.objects.get_or_create(iso3=iso3, defaults={"name": cname})
        # If name ever changes, keep DB in sync.
        if country.name != cname:
            country.name = cname
            country.save(update_fields=["name"])
        countries_by_name[cname] = country

    existing_zone_codes = set(Zone.objects.values_list("code", flat=True))
    zones_to_create = []
    for zcode, cname in zone_rows:
        if zcode in existing_zone_codes:
            continue
        country = countries_by_name.get(cname)
        if not country:
            continue
        zones_to_create.append(Zone(code=zcode, country=country))

    if zones_to_create:
        Zone.objects.bulk_create(zones_to_create)


def unseed(apps, schema_editor):
    Country = apps.get_model("selector", "Country")
    Zone = apps.get_model("selector", "Zone")
    Zone.objects.all().delete()
    Country.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("selector", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]

