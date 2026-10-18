"""Generate the synthetic supplier / BOM dataset.

All supplier and customer names are fictional. Country risk values are
illustrative approximations inspired by public governance indices.
Run: python data/seed.py
"""
import csv
import json
from pathlib import Path

OUT = Path(__file__).parent

# id, name, country, city, lat, lon, category, tier, feeds (tier-2 -> tier-1 ids),
# spend_meur, financial_score (0-100, higher = healthier), quality_ppm, ncr_12m,
# otd_6m (oldest -> newest, %), stock_days, lead_time_weeks, certs, keywords, note
SUPPLIERS = [
    ("S01", "Bohemia Steel Castings a.s.", "CZ", "Ostrava", 49.82, 18.26, "Bogie frames & castings", 1, [],
     38.0, 31, 1800, 9, [94, 92, 90, 86, 83, 79], 20, 26,
     {"ISO 9001": "2027-06-30", "ISO/TS 22163": "2027-03-31", "EN 15085-2": "2027-01-31"},
     "Czech steel foundry insolvency energy prices Ostrava",
     "Sole qualified source for bogie frames. Lost two large automotive contracts in 2026."),
    ("S02", "Rheinland Radsatz GmbH", "DE", "Duisburg", 51.43, 6.76, "Wheelsets", 1, [],
     22.0, 74, 420, 2, [97, 96, 97, 98, 96, 97], 35, 18,
     {"ISO 9001": "2028-02-28", "ISO/TS 22163": "2027-09-30", "EN 15085-2": "2027-11-30"},
     "Duisburg steel industry strike railway wheels", ""),
    ("S03", "Alpen Bremstechnik GmbH", "AT", "Linz", 48.31, 14.29, "Brake control units", 1, [],
     29.0, 81, 260, 1, [98, 97, 98, 97, 98, 97], 30, 22,
     {"ISO 9001": "2027-08-31", "ISO/TS 22163": "2027-05-31", "EN 15085-2": "2026-11-06"},
     "Austria rail brake manufacturer Linz industry", "EN 15085-2 welding certificate renewal audit not yet scheduled."),
    ("S04", "Lombardia Freni S.p.A.", "IT", "Brescia", 45.54, 10.21, "Brake discs & pads", 1, [],
     11.0, 66, 610, 3, [95, 95, 94, 96, 95, 94], 40, 12,
     {"ISO 9001": "2027-10-31", "ISO/TS 22163": "2027-07-31"},
     "Brescia Lombardy manufacturing flood strike", ""),
    ("S05", "Elektra Traktion GmbH", "DE", "Nuremberg", 49.45, 11.08, "Traction converters", 1, [],
     64.0, 78, 350, 2, [96, 97, 96, 95, 96, 96], 25, 30,
     {"ISO 9001": "2027-12-31", "ISO/TS 22163": "2027-06-30", "EN 50155": "2027-04-30"},
     "traction converter power electronics shortage Germany", "Depends on a single IGBT module source in Penang."),
    ("S06", "Hanse Transformatoren GmbH", "DE", "Dresden", 51.05, 13.74, "Main transformers", 1, [],
     41.0, 70, 300, 1, [93, 94, 95, 94, 95, 95], 30, 40,
     {"ISO 9001": "2027-05-31", "ISO/TS 22163": "2027-02-28"},
     "transformer shortage grain oriented electrical steel copper", ""),
    ("S07", "Vltava Motors s.r.o.", "CZ", "Plzen", 49.74, 13.37, "Traction motors", 1, [],
     47.0, 69, 480, 3, [95, 94, 95, 93, 94, 93], 28, 28,
     {"ISO 9001": "2027-09-30", "ISO/TS 22163": "2027-08-31", "EN 50155": "2027-03-31"},
     "permanent magnet traction motor rare earth supply Czech", "Permanent-magnet motors need NdFeB magnets from China."),
    ("S08", "Anatolia Klima A.S.", "TR", "Bursa", 40.19, 29.06, "HVAC units", 1, [],
     19.0, 52, 950, 6, [92, 90, 91, 88, 87, 86], 21, 16,
     {"ISO 9001": "2027-01-31", "ISO/TS 22163": "2027-04-30", "EN 45545-2": "2026-09-30"},
     "Turkey lira inflation manufacturing Bursa earthquake", "EN 45545-2 fire safety certificate expired."),
    ("S09", "Silesia Doors Sp. z o.o.", "PL", "Wroclaw", 51.11, 17.03, "Passenger door systems", 1, [],
     24.0, 71, 520, 2, [96, 95, 96, 95, 96, 95], 30, 14,
     {"ISO 9001": "2027-11-30", "ISO/TS 22163": "2027-10-31", "EN 45545-2": "2027-06-30"},
     "Poland manufacturing labour shortage Wroclaw", ""),
    ("S10", "Catalunya Interiors S.L.", "ES", "Barcelona", 41.39, 2.17, "Seats & interior panels", 1, [],
     16.0, 63, 700, 4, [94, 95, 93, 94, 95, 94], 35, 10,
     {"ISO 9001": "2027-03-31", "ISO/TS 22163": "2027-01-31", "EN 45545-2": "2027-02-28"},
     "Barcelona port strike Catalonia industry", ""),
    ("S11", "Lviv Cable Systems LLC", "UA", "Lviv", 49.84, 24.03, "Cable harnesses", 1, [],
     14.0, 49, 820, 5, [95, 93, 94, 90, 89, 87], 18, 10,
     {"ISO 9001": "2027-02-28", "ISO/TS 22163": "2027-03-31", "EN 45545-2": "2027-05-31"},
     "Lviv Ukraine power outage drone strike factory", "Diesel generators cover outages, at higher cost."),
    ("S12", "Danube Wiring d.o.o.", "RS", "Novi Sad", 45.26, 19.83, "Cable harnesses", 1, [],
     6.0, 64, 640, 2, [96, 96, 95, 96, 95, 96], 25, 10,
     {"ISO 9001": "2027-07-31", "ISO/TS 22163": "2027-12-31", "EN 45545-2": "2027-08-31"},
     "Serbia Novi Sad manufacturing protests energy", ""),
    ("S13", "Nordic Aluminium Profiles AS", "NO", "Raufoss", 60.72, 10.61, "Car body extrusions", 1, [],
     33.0, 83, 210, 1, [97, 98, 97, 97, 98, 98], 30, 20,
     {"ISO 9001": "2028-01-31", "ISO/TS 22163": "2027-11-30", "EN 15085-2": "2027-10-31"},
     "aluminium price Europe smelter energy Norway", ""),
    ("S14", "Helvetia Pantograph AG", "CH", "Winterthur", 47.50, 8.72, "Pantographs", 1, [],
     9.0, 86, 150, 0, [99, 98, 99, 99, 98, 99], 45, 16,
     {"ISO 9001": "2028-03-31", "ISO/TS 22163": "2027-12-31"},
     "Switzerland rail supplier Winterthur", ""),
    ("S15", "Glaswerk Thueringen GmbH", "DE", "Jena", 50.93, 11.59, "Windscreens & side windows", 1, [],
     8.0, 68, 390, 2, [96, 96, 97, 95, 96, 96], 40, 14,
     {"ISO 9001": "2027-06-30", "ISO/TS 22163": "2027-04-30", "EN 45545-2": "2027-09-30"},
     "Germany glass industry gas prices", ""),
    ("S16", "Kanto Rail Electronics K.K.", "JP", "Yokohama", 35.44, 139.64, "Train control computers", 1, [],
     27.0, 88, 120, 0, [98, 99, 98, 99, 99, 98], 50, 24,
     {"ISO 9001": "2028-05-31", "ISO/TS 22163": "2028-01-31", "EN 50155": "2027-12-31"},
     "Japan earthquake Yokohama electronics chip supply", ""),
    ("S17", "Shenzhen Volta Energy Co., Ltd.", "CN", "Shenzhen", 22.54, 114.06, "Traction battery packs", 1, [],
     36.0, 72, 330, 2, [95, 96, 94, 95, 93, 94], 30, 20,
     {"ISO 9001": "2027-08-31", "ISO/TS 22163": "2027-02-28", "EN 50155": "2027-06-30"},
     "China export controls battery graphite EU tariffs", "Exposure to EU-China trade measures on batteries."),
    ("S18", "Maple Hydrogen Systems Inc.", "CA", "Vancouver", 49.28, -123.12, "Fuel cell modules", 1, [],
     52.0, 58, 560, 4, [93, 92, 94, 91, 92, 90], 25, 34,
     {"ISO 9001": "2027-04-30", "ISO/TS 22163": "2027-03-31"},
     "hydrogen fuel cell company layoffs funding Canada", "Sole source for Mireo Plus H fuel cells. Hydrogen sector funding is tightening."),
    ("S19", "Gaul Couplers SAS", "FR", "Lille", 50.63, 3.06, "Couplers & gangways", 1, [],
     12.0, 75, 300, 1, [97, 96, 97, 96, 97, 97], 40, 18,
     {"ISO 9001": "2027-10-31", "ISO/TS 22163": "2027-06-30", "EN 15085-2": "2027-09-30"},
     "France strike Lille industry rail", ""),
    ("S20", "Baltic Fire Safety UAB", "LT", "Kaunas", 54.90, 23.90, "Fire detection systems", 1, [],
     4.0, 70, 280, 1, [97, 97, 96, 97, 97, 96], 45, 8,
     {"ISO 9001": "2027-09-30", "ISO/TS 22163": "2027-07-31", "EN 45545-2": "2027-11-30"},
     "Lithuania Kaunas electronics manufacturing", ""),
    ("S21", "Penang PowerSemi Sdn. Bhd.", "MY", "Penang", 5.41, 100.33, "IGBT power modules", 2, ["S05"],
     0.0, 67, 90, 1, [97, 96, 97, 95, 96, 96], 35, 36,
     {"ISO 9001": "2027-05-31", "IATF 16949": "2027-03-31"},
     "Penang Malaysia semiconductor plant flood fire power outage", "Only qualified IGBT module for Elektra converters."),
    ("S22", "Bavaria Info Displays GmbH", "DE", "Augsburg", 48.37, 10.90, "Passenger information systems", 1, [],
     7.0, 73, 410, 2, [96, 95, 96, 96, 95, 96], 30, 12,
     {"ISO 9001": "2027-12-31", "ISO/TS 22163": "2027-08-31", "EN 50155": "2027-05-31"},
     "Germany display electronics supplier", ""),
    ("S23", "Hsinchu Display Tech Corp.", "TW", "Hsinchu", 24.80, 120.97, "TFT display panels", 2, ["S22"],
     0.0, 80, 150, 0, [98, 97, 98, 98, 97, 98], 40, 16,
     {"ISO 9001": "2027-10-31"},
     "Taiwan strait tensions Hsinchu semiconductor earthquake", ""),
    ("S24", "Pune Precision Bearings Pvt. Ltd.", "IN", "Pune", 18.52, 73.86, "Axle bearings", 1, [],
     10.0, 62, 540, 3, [93, 94, 92, 93, 94, 92], 30, 20,
     {"ISO 9001": "2027-06-30", "ISO/TS 22163": "2027-02-28"},
     "India Pune manufacturing monsoon flood export", ""),
    ("S25", "Goeteborg Lager AB", "SE", "Gothenburg", 57.71, 11.97, "Axle bearings", 1, [],
     8.0, 85, 180, 0, [98, 98, 99, 98, 98, 99], 40, 18,
     {"ISO 9001": "2028-02-29", "ISO/TS 22163": "2027-11-30"},
     "Sweden Gothenburg port strike industry", ""),
    ("S26", "Monterrey Forge S.A. de C.V.", "MX", "Monterrey", 25.69, -100.32, "Forged axles", 1, [],
     13.0, 60, 620, 3, [94, 93, 94, 92, 93, 91], 35, 22,
     {"ISO 9001": "2027-04-30", "ISO/TS 22163": "2027-01-31"},
     "Mexico tariffs steel Monterrey manufacturing", ""),
    ("S27", "Busan Power Cable Co., Ltd.", "KR", "Busan", 35.18, 129.08, "High-voltage roof cables", 1, [],
     5.0, 79, 200, 0, [97, 98, 97, 97, 98, 97], 40, 14,
     {"ISO 9001": "2027-11-30", "ISO/TS 22163": "2027-09-30", "EN 45545-2": "2027-10-31"},
     "Busan port Korea cable manufacturer strike", ""),
    ("S28", "Transilvania Composite SRL", "RO", "Cluj-Napoca", 46.77, 23.60, "Composite front-end masks", 1, [],
     6.0, 57, 880, 5, [94, 92, 93, 91, 90, 90], 25, 16,
     {"ISO 9001": "2027-03-31", "ISO/TS 22163": "2026-12-10", "EN 45545-2": "2027-04-30"},
     "Romania Cluj manufacturing composites", "ISO/TS 22163 recertification audit due in December."),
    ("S29", "Magyar Gearbox Kft.", "HU", "Gyor", 47.68, 17.63, "Gearboxes", 1, [],
     21.0, 68, 450, 2, [96, 95, 96, 95, 95, 94], 30, 24,
     {"ISO 9001": "2027-07-31", "ISO/TS 22163": "2027-05-31"},
     "Hungary Gyor automotive industry", ""),
    ("S30", "Ruhr Spezialstahl GmbH", "DE", "Bochum", 51.48, 7.22, "Steel plate & forgings", 2, ["S01", "S02"],
     0.0, 61, 300, 1, [95, 94, 95, 94, 93, 94], 30, 12,
     {"ISO 9001": "2027-08-31"},
     "German steel industry crisis Ruhr blast furnace", ""),
    ("S31", "Ganzhou Rare Earth Magnets Co.", "CN", "Ganzhou", 25.83, 114.93, "NdFeB permanent magnets", 2, ["S07"],
     0.0, 70, 120, 0, [97, 96, 97, 97, 96, 97], 45, 20,
     {"ISO 9001": "2027-09-30"},
     "China rare earth export controls magnets", "Rare earth magnets are subject to Chinese export licensing."),
    ("S32", "Andes Copper Rod S.A.", "CL", "Antofagasta", -23.65, -70.40, "Copper rod", 2, ["S11", "S12", "S27", "S06"],
     0.0, 77, 50, 0, [96, 97, 96, 96, 97, 96], 30, 10,
     {"ISO 9001": "2027-12-31"},
     "Chile copper mine strike Antofagasta copper price", ""),
]

PROJECTS = [
    {"id": "P1", "name": "Velaro Novo", "customer": "Iberia HighSpeed (fictional)", "type": "High-speed train",
     "units": 10, "delivery": "2027-05-31", "penalty_per_day_eur": 90000, "contract_value_meur": 320, "slack_days": 21},
    {"id": "P2", "name": "Mireo Plus H", "customer": "Nordbahn Regional (fictional)", "type": "Hydrogen regional train",
     "units": 20, "delivery": "2027-03-15", "penalty_per_day_eur": 35000, "contract_value_meur": 240, "slack_days": 14},
    {"id": "P3", "name": "Vectron MS", "customer": "CargoLink Europe (fictional)", "type": "Multi-system locomotive",
     "units": 25, "delivery": "2027-01-31", "penalty_per_day_eur": 20000, "contract_value_meur": 100, "slack_days": 10},
    {"id": "P4", "name": "Inspiro Metro", "customer": "Capital Metro Authority (fictional)", "type": "Metro train",
     "units": 16, "delivery": "2027-08-30", "penalty_per_day_eur": 45000, "contract_value_meur": 210, "slack_days": 30},
]

ALL = ["P1", "P2", "P3", "P4"]
PASSENGER = ["P1", "P2", "P4"]
AC_FED = ["P1", "P2", "P3"]  # need main transformer + pantograph

# component, [(supplier, share)], projects, unit_cost_eur, required certs
BOM = [
    ("Bogie frame", [("S01", 1.0)], ALL, 48000, ["ISO/TS 22163", "EN 15085-2"]),
    ("Wheelset", [("S02", 1.0)], ALL, 21000, ["ISO/TS 22163", "EN 15085-2"]),
    ("Forged axle", [("S26", 1.0)], ALL, 6500, ["ISO/TS 22163"]),
    ("Axle bearing", [("S24", 0.6), ("S25", 0.4)], ALL, 2400, ["ISO/TS 22163"]),
    ("Brake control unit", [("S03", 1.0)], ALL, 18000, ["ISO/TS 22163", "EN 15085-2"]),
    ("Brake discs & pads", [("S04", 1.0)], ALL, 3200, ["ISO/TS 22163"]),
    ("Traction motor", [("S07", 1.0)], ALL, 62000, ["ISO/TS 22163", "EN 50155"]),
    ("Gearbox", [("S29", 1.0)], ALL, 27000, ["ISO/TS 22163"]),
    ("Traction converter", [("S05", 1.0)], ALL, 240000, ["ISO/TS 22163", "EN 50155"]),
    ("Main transformer", [("S06", 1.0)], AC_FED, 310000, ["ISO/TS 22163"]),
    ("Pantograph", [("S14", 1.0)], AC_FED + ["P4"], 24000, ["ISO/TS 22163"]),
    ("HVAC unit", [("S08", 1.0)], ALL, 45000, ["ISO/TS 22163", "EN 45545-2"]),
    ("Passenger door system", [("S09", 1.0)], PASSENGER, 15000, ["ISO/TS 22163", "EN 45545-2"]),
    ("Seats & interior panels", [("S10", 1.0)], PASSENGER, 90000, ["ISO/TS 22163", "EN 45545-2"]),
    ("Cable harness", [("S11", 0.7), ("S12", 0.3)], ALL, 38000, ["ISO/TS 22163", "EN 45545-2"]),
    ("Car body extrusions", [("S13", 1.0)], PASSENGER, 120000, ["ISO/TS 22163", "EN 15085-2"]),
    ("Windscreen & windows", [("S15", 1.0)], ALL, 22000, ["ISO/TS 22163", "EN 45545-2"]),
    ("Train control computer", [("S16", 1.0)], ALL, 85000, ["ISO/TS 22163", "EN 50155"]),
    ("Traction battery pack", [("S17", 1.0)], ["P2"], 410000, ["ISO/TS 22163", "EN 50155"]),
    ("Fuel cell module", [("S18", 1.0)], ["P2"], 680000, ["ISO/TS 22163"]),
    ("Couplers & gangways", [("S19", 1.0)], ALL, 34000, ["ISO/TS 22163", "EN 15085-2"]),
    ("Fire detection system", [("S20", 1.0)], PASSENGER, 9000, ["ISO/TS 22163", "EN 45545-2"]),
    ("Passenger information system", [("S22", 1.0)], PASSENGER, 26000, ["ISO/TS 22163", "EN 50155"]),
    ("HV roof cable", [("S27", 1.0)], AC_FED, 7000, ["ISO/TS 22163", "EN 45545-2"]),
    ("Composite front-end mask", [("S28", 1.0)], ["P1", "P2", "P4"], 52000, ["ISO/TS 22163", "EN 45545-2"]),
]

# component, alternative, country, status, qualification_months, price_delta_pct, note
ALTERNATIVES = [
    ("Bogie frame", "Moravia Foundry s.r.o.", "CZ", "In qualification", 9, 6, "First article inspection passed in August"),
    ("Bogie frame", "Saxon Welded Structures GmbH", "DE", "Not qualified", 16, 14, "Has EN 15085-2 CL1, no rail bogie references"),
    ("Brake control unit", "Nordic Brake Systems AB", "SE", "Qualified", 0, 9, "Qualified for Vectron, capacity 40 units/month"),
    ("HVAC unit", "Iberclima Rail S.A.", "ES", "Qualified", 0, 11, "Holds valid EN 45545-2"),
    ("HVAC unit", "Thermo Rail Polska", "PL", "In qualification", 6, 4, "Prototype test passed"),
    ("Cable harness", "Danube Wiring d.o.o.", "RS", "Qualified", 0, 3, "Already supplies 30%, can ramp to 60% in 8 weeks"),
    ("Cable harness", "Morava Kabel s.r.o.", "CZ", "In qualification", 5, 7, ""),
    ("IGBT power modules", "Bavarian Power Devices GmbH", "DE", "In qualification", 10, 18, "Converter redesign of the gate driver needed"),
    ("IGBT power modules", "Kyushu Semicon Ltd.", "JP", "Not qualified", 14, 12, ""),
    ("Fuel cell module", "Rhein Hydrogen Power GmbH", "DE", "Not qualified", 18, 22, "Prototype stage"),
    ("Composite front-end mask", "Adria Composites d.o.o.", "HR", "Qualified", 0, 8, ""),
    ("Traction battery pack", "Silesia Battery Systems", "PL", "In qualification", 8, 15, "Uses EU-made cells"),
    ("NdFeB permanent magnets", "Estonia Magnet Works", "EE", "In qualification", 12, 35, "EU rare earth processing, limited volume"),
    ("Main transformer", "Adriatic Transformers d.d.", "HR", "Qualified", 0, 5, "Lead time 44 weeks"),
    ("Traction motor", "Asynchronous motor variant (Vltava)", "CZ", "Qualified", 0, -3, "Induction motor, no rare earth magnets, 4% lower efficiency"),
]

COUNTRY_RISK = [
    ("DE", "Germany", 12), ("AT", "Austria", 10), ("CH", "Switzerland", 6), ("SE", "Sweden", 8),
    ("NO", "Norway", 7), ("CZ", "Czechia", 22), ("PL", "Poland", 25), ("IT", "Italy", 30),
    ("ES", "Spain", 24), ("FR", "France", 20), ("LT", "Lithuania", 28), ("HU", "Hungary", 38),
    ("RO", "Romania", 40), ("RS", "Serbia", 52), ("TR", "Turkey", 64), ("UA", "Ukraine", 88),
    ("MY", "Malaysia", 42), ("TW", "Taiwan", 55), ("CN", "China", 62), ("JP", "Japan", 15),
    ("KR", "South Korea", 25), ("IN", "India", 48), ("MX", "Mexico", 55), ("CA", "Canada", 10),
    ("CL", "Chile", 35), ("HR", "Croatia", 30), ("EE", "Estonia", 22),
]


def main():
    suppliers = []
    for s in SUPPLIERS:
        (sid, name, cc, city, lat, lon, cat, tier, feeds, spend, fin, ppm, ncr, otd,
         stock, lead, certs, kw, note) = s
        suppliers.append({
            "id": sid, "name": name, "country": cc, "city": city, "lat": lat, "lon": lon,
            "category": cat, "tier": tier, "feeds": feeds, "spend_meur": spend,
            "financial_score": fin, "quality_ppm": ppm, "ncr_12m": ncr, "otd_6m": otd,
            "stock_days": stock, "lead_time_weeks": lead, "certs": certs,
            "search_keywords": kw, "note": note,
        })
    (OUT / "suppliers.json").write_text(json.dumps(suppliers, indent=2))
    (OUT / "projects.json").write_text(json.dumps(PROJECTS, indent=2))

    with open(OUT / "bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["project_id", "component", "supplier_id", "share", "unit_cost_eur", "required_certs"])
        for comp, sources, projects, cost, certs in BOM:
            for pid in projects:
                for sid, share in sources:
                    w.writerow([pid, comp, sid, share, cost, ";".join(certs)])

    with open(OUT / "alternatives.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["component", "alternative", "country", "status", "qualification_months", "price_delta_pct", "note"])
        w.writerows(ALTERNATIVES)

    with open(OUT / "country_risk.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["country", "name", "risk"])
        w.writerows(COUNTRY_RISK)
    print(f"wrote {len(suppliers)} suppliers, {len(PROJECTS)} projects, {len(BOM)} components")


if __name__ == "__main__":
    main()
