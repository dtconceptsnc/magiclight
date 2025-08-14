#!/usr/bin/env python3
# baseline_core.py  – ship this once with your model

import csv, argparse, importlib.util, os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from astral import LocationInfo
from astral.sun import elevation as elevation

# dynamic import of brain.py
spec = importlib.util.spec_from_file_location("brain", "../brain.py")
brain = importlib.util.module_from_spec(spec); spec.loader.exec_module(brain)  # type: ignore

def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--tz",  required=True)
    p.add_argument("--start", required=True)     # YYYY-MM-DD
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--out",  default="baseline_core.csv")
    return p.parse_args()

def main():
    a = parse(); tz = ZoneInfo(a.tz)
    start = datetime.combine(date.fromisoformat(a.start), datetime.min.time(), tz)
    end   = start + timedelta(days=a.days); step = timedelta(minutes=1)

    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp_utc","solar_elev_deg","brightness_pct","color_temp_k"])
        loc = LocationInfo(latitude=a.lat, longitude=a.lon, timezone=a.tz)

        ts = start
        while ts < end:
            res  = brain.get_adaptive_lighting(latitude=a.lat, longitude=a.lon,
                                               timezone=a.tz, current_time=ts)
            elev = elevation(loc.observer, ts)
            w.writerow([
                ts.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds"),
                round(elev,2), res["brightness"], res["color_temp"]
            ])
            ts += step
    print(f"[baseline_core] wrote {a.out}")

if __name__ == "__main__":
    main()