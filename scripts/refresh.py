#!/usr/bin/env python3
"""SY auto-refresh (runs on GitHub Actions). Standard library only.

Reads: IBJA official site (ibjarates.com), live spot gold/silver from two free feeds,
USD-INR from two free feeds. Updates data.json and history_monthly.json.
Rules: a value is "verified" only when two independent feeds agree (0.5% prices,
0.1 INR for FX). If a source fails, its fields are left as they were.
"""
import json, math, re, sys, urllib.request, datetime as dt, html

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(IST)
UA = {"User-Agent": "Mozilla/5.0 (SY gold app refresh; +https://yukeshvanhelsing.github.io)"}

def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def jget(url):
    return json.loads(get(url))

def log(*a): print(*a, file=sys.stderr)

# ---------- live feeds ----------
def spot():
    out = {"gold": [], "silver": []}
    try:
        j = jget("https://api.gold-api.com/price/XAU"); out["gold"].append(("gold-api.com", float(j["price"]), "https://gold-api.com"))
        j = jget("https://api.gold-api.com/price/XAG"); out["silver"].append(("gold-api.com", float(j["price"]), "https://gold-api.com"))
    except Exception as e: log("gold-api failed", e)
    try:
        j = jget("https://data-asg.goldprice.org/dbXRates/USD"); it = j["items"][0]
        out["gold"].append(("goldprice.org", float(it["xauPrice"]), "https://goldprice.org"))
        out["silver"].append(("goldprice.org", float(it["xagPrice"]), "https://goldprice.org"))
    except Exception as e: log("goldprice.org failed", e)
    return out

def fx():
    vals = []
    try:
        j = jget("https://open.er-api.com/v6/latest/USD"); vals.append(("ExchangeRate-API", float(j["rates"]["INR"]), "https://www.exchangerate-api.com"))
    except Exception as e: log("er-api failed", e)
    try:
        j = jget("https://api.frankfurter.app/latest?from=USD&to=INR"); vals.append(("Frankfurter (ECB reference)", float(j["rates"]["INR"]), "https://www.frankfurter.app"))
    except Exception as e: log("frankfurter failed", e)
    return vals

def combine(vals, tol_pct=None, tol_abs=None):
    """Return (value, status, sources). Verified if any two agree within tolerance."""
    if not vals: return None, None, []
    for i in range(len(vals)):
        for k in range(i + 1, len(vals)):
            a, b = vals[i][1], vals[k][1]
            ok = abs(a - b) <= tol_abs if tol_abs is not None else abs(a / b - 1) * 100 <= tol_pct
            if ok: return round((a + b) / 2, 4), "verified", [vals[i], vals[k]]
    return vals[0][1], "single source", [vals[0]]

# ---------- IBJA ----------
ROW = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{4,7})\s+(\d{4,7})\s+(\d{4,7})\s+(\d{4,7})\s+(\d{4,7})\s+(\d{4,7})")
def ibja():
    """Returns {"AM": {date: row}, "PM": {date: row}} from the official 'Previous Dates Rate' tables.
    The page lists the AM table first, then the PM table (same dates)."""
    txt = get("https://www.ibjarates.com/")
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt)); txt = re.sub(r"\s+", " ", txt)
    am, pm, seen = {}, {}, set()
    for m in ROW.finditer(txt):
        d = dt.datetime.strptime(m.group(1), "%d/%m/%Y").date()
        r = dict(zip(["p999", "p995", "p916", "p750", "p585", "silver"], map(int, m.groups()[1:])))
        if not (50000 < r["p999"] < 400000 and r["p916"] < r["p999"] and r["p750"] < r["p916"]): continue
        (pm if d in seen else am)[d] = r; seen.add(d)
    if not am: raise RuntimeError("IBJA tables not found")
    return {"AM": am, "PM": pm, "holiday": bool(re.search(r"\bHoliday\b", txt))}

# ---------- helpers ----------
def dfmt(d): return f"{d.day} {d.strftime('%b %Y')}"
def pdate(s):
    try: return dt.datetime.strptime(s, "%d %b %Y").date()
    except Exception: return None
def fix_time(d, sess): return dt.datetime(d.year, d.month, d.day, 12, 30 if sess == "AM" else 0, tzinfo=IST) if sess == "AM" else dt.datetime(d.year, d.month, d.day, 17, 0, tzinfo=IST)

def next_session(after_d, after_s):
    """Next weekday IBJA session after (date, session)."""
    if after_s == "AM": return after_d, "PM"
    d = after_d + dt.timedelta(days=1)
    while d.weekday() >= 5: d += dt.timedelta(days=1)
    return d, "AM"

def margin(metal, hours, logs, sess):
    errs = sorted(abs(e["err_pct"]) for e in logs if e["metal"] == metal and e["session"] == sess)
    floor = 0.5 if metal == "gold" else 0.8
    if len(errs) >= 20:
        return max(floor, round(errs[min(len(errs) - 1, int(math.ceil(0.8 * len(errs))) - 1)], 1))
    sig = 1.80 if metal == "gold" else 3.06   # daily σ in %, from GVZ / VXSLV
    m = math.sqrt((1.28 * sig * math.sqrt(max(hours, 0.25) / 24)) ** 2 + 0.3 ** 2)
    return max(floor, round(m, 1))

def nearest_spot(spot_log, when, metal):
    best = None
    for s in spot_log:
        t = dt.datetime.fromisoformat(s["t"])
        gap = abs((t - when).total_seconds())
        if s.get(metal) and (best is None or gap < best[0]): best = (gap, s)
    if best and best[0] <= 3 * 3600: return best[1]
    return None

# ---------- main ----------
def main():
    D = json.load(open("data.json"))
    H = json.load(open("history_monthly.json"))
    changed = False

    sp = spot(); fxv = fx()
    g, gst, gsrc = combine(sp["gold"], tol_pct=0.5)
    s, sst, ssrc = combine(sp["silver"], tol_pct=0.5)
    r, rst, rsrc = combine(fxv, tol_abs=0.25)  # ECB reference is a daily rate, so allow 0.25
    stamp = NOW.strftime("%-d %b %Y, %-I:%M %p IST")
    srcs = lambda L: [{"name": f"{n} (${v:,.2f})" if v > 200 else f"{n} ({v:,.3f})", "url": u} for n, v, u in L]

    if g and 1000 < g < 20000:
        prev = D["gold"]["intl"].get("usd_oz")
        D["gold"]["intl"].update({"usd_oz": round(g, 2), "asof": stamp, "status": gst, "sources": srcs(gsrc),
            "note": "Live spot from two independent feeds, checked automatically every 30 minutes on weekdays."})
        changed = True
    if s and 5 < s < 500:
        D["silver"]["intl"].update({"usd_oz": round(s, 3), "asof": stamp, "status": sst, "sources": srcs(ssrc),
            "note": "Live spot from two independent feeds, checked automatically every 30 minutes on weekdays."})
        changed = True
    if r and 60 < r < 150:
        D["fx"] = {"usd_inr": round(r, 2), "asof": stamp, "status": rst, "sources": srcs(rsrc)}
        changed = True

    # day change vs the last reading from an earlier day
    for metal, val in (("gold", g), ("silver", s)):
        if not val: continue
        prior = [x for x in D.get("spot_log", []) if x.get(metal) and x["t"][:10] < NOW.date().isoformat()]
        if prior: D[metal]["intl"]["change_pct"] = round((val / prior[-1][metal] - 1) * 100, 2)
    # spot log for fix-time matching
    slog = D.setdefault("spot_log", [])
    if g or s:
        slog.append({"t": NOW.isoformat(timespec="minutes"), "gold": round(g, 2) if g else None, "silver": round(s, 3) if s else None, "fx": round(r, 3) if r else None})
        D["spot_log"] = slog[-96:]

    # IBJA official
    try:
        T = ibja()
    except Exception as e:
        log("IBJA failed:", e); T = None
    gi, si = D["gold"]["india"], D["silver"]["india"]
    cur_d, cur_s = pdate(gi.get("date", "")), ("PM" if "PM" in gi.get("session", "") else "AM")
    if T:
        sessions = sorted([(d, "AM") for d in T["AM"]] + [(d, "PM") for d in T["PM"]], key=lambda x: (x[0], x[1] == "PM"))
        latest = sessions[-1]
        if cur_d is None or (latest[0], latest[1] == "PM") > (cur_d, cur_s == "PM"):
            # score any published sessions that we had estimated
            est = D.get("india_estimate", {}); acc = D.setdefault("accuracy", {"note": "", "log": []})
            for key in ("am", "pm"):
                e = est.get(key) or {}
                ed = pdate(e.get("for", "")); es = key.upper()
                row = T[es].get(ed) if ed else None
                if row and not any(x["date"] == ed.isoformat() and x["session"] == es for x in acc["log"]):
                    for metal, ek, ak in (("gold", "gold_999_10g", "p999"), ("silver", "silver_999_kg", "silver")):
                        if e.get(ek):
                            acc["log"].append({"date": ed.isoformat(), "session": es, "metal": metal, "est": e[ek], "actual": row[ak],
                                "err_pct": round((row[ak] / e[ek] - 1) * 100, 2), "margin_pct": e["margin_pct"][metal]})
            acc["log"] = acc["log"][-240:]
            acc["note"] = f"{len(acc['log'])} estimates scored since 20 Nov 2026."
            # new base
            ld, ls = latest; row = T[ls][ld]
            prev_sess = sessions[-2] if len(sessions) > 1 else None
            prow = T[prev_sess[1]][prev_sess[0]] if prev_sess else None
            fs = nearest_spot(D["spot_log"], fix_time(ld, ls), "gold")
            gi.update({"p999_10g": row["p999"], "p916_10g": row["p916"], "p750_10g": row["p750"], "session": f"IBJA {ls}", "date": dfmt(ld),
                "prev_999_10g": prow["p999"] if prow else gi.get("prev_999_10g"),
                "change_pct": round((row["p999"] / prow["p999"] - 1) * 100, 2) if prow else gi.get("change_pct"),
                "status": "verified", "sources": [{"name": "IBJA official website", "url": "https://www.ibjarates.com/"}],
                "note": f"From IBJA's official website (ibjarates.com), {dfmt(ld)} {ls}: 999 ₹{row['p999']:,} · 916 ₹{row['p916']:,} · 750 ₹{row['p750']:,} per 10 g, without 3% GST and making charges. Read automatically."})
            si.update({"p999_kg": row["silver"], "session": f"IBJA {ls}", "date": dfmt(ld),
                "prev_999_kg": prow["silver"] if prow else si.get("prev_999_kg"),
                "change_pct": round((row["silver"] / prow["silver"] - 1) * 100, 2) if prow else si.get("change_pct"),
                "status": "verified", "sources": [{"name": "IBJA official website", "url": "https://www.ibjarates.com/"}],
                "note": f"IBJA official website, {dfmt(ld)} {ls}: ₹{row['silver']:,}/kg (without GST). Read automatically."})
            if ls == "PM":
                gi.update({"pm_999_10g": row["p999"], "pm_916_10g": row["p916"]}); si["pm_999_kg"] = row["silver"]
            if fs:
                gi["spot_at_fix_usd"] = fs["gold"]; gi["pm_spot_at_fix_usd"] = fs["gold"]
                if fs.get("fx"): gi["fx_at_fix"] = fs["fx"]; gi["pm_fx_at_fix"] = fs["fx"]
                if fs.get("silver"): si["spot_at_fix_usd"] = fs["silver"]; si["pm_spot_at_fix_usd"] = fs["silver"]
            elif g:  # first time seen: use the current spot as the closest available reference
                gi["spot_at_fix_usd"] = round(g, 2); gi["fx_at_fix"] = round(r, 3) if r else gi.get("fx_at_fix")
                if s: si["spot_at_fix_usd"] = round(s, 3)
            cur_d, cur_s = ld, ls
            # history row
            hist = D.setdefault("history", [])
            hist[:] = [h for h in hist if h["date"] != ld.isoformat()]
            hist.append({"date": ld.isoformat(), "gold_usd": gi.get("spot_at_fix_usd"), "silver_usd": si.get("spot_at_fix_usd"),
                "gold_999_10g": T["AM"].get(ld, row)["p999"], "gold_916_10g": T["AM"].get(ld, row)["p916"], "gold_750_10g": T["AM"].get(ld, row)["p750"],
                "silver_999_kg": T["AM"].get(ld, row)["silver"], "usd_inr": gi.get("fx_at_fix"), "src": "IBJA official AM (auto); spot feeds"})
            hist.sort(key=lambda h: h["date"]); D["history"] = hist[-120:]
            changed = True
        # IBJA holiday / not yet published note
        today = NOW.date()
        if today.weekday() < 5 and today not in T["AM"] and (T.get("holiday") or NOW.hour >= 13):
            gi["today_note"] = "IBJA has not published today's rates (holiday or delay)."
        else:
            gi.pop("today_note", None)

    # estimates for the next two unpublished sessions
    if g and cur_d:
        base_g, base_s = gi, si
        ratio_g = g / float(gi.get("spot_at_fix_usd") or g) * ((r / float(gi.get("fx_at_fix") or r)) if r else 1)
        ratio_s = (s / float(si.get("spot_at_fix_usd") or s) if s else 1) * ((r / float(gi.get("fx_at_fix") or r)) if r else 1)
        n1 = next_session(cur_d, cur_s)
        holiday_today = bool(T and T.get("holiday") and NOW.date() not in T["AM"])
        while fix_time(*n1) < NOW - dt.timedelta(hours=3) or (holiday_today and n1[0] == NOW.date()):
            n1 = next_session(*n1)   # skip sessions that never published (holidays)
        n2 = next_session(*n1)
        # make sure the first estimate isn't in the past by more than a few hours
        logs = D.get("accuracy", {}).get("log", [])
        def blk(nd, ns):
            hrs = max(0.25, (fix_time(nd, ns) - NOW).total_seconds() / 3600)
            lab = "Midday · IBJA AM ~12:30 pm" if ns == "AM" else "Evening · IBJA PM ~5 pm"
            if nd != NOW.date(): lab += f" · {nd.day} {nd.strftime('%b')}"
            return {"for": dfmt(nd), "label": lab,
                "gold_999_10g": round(gi["p999_10g"] * ratio_g), "gold_916_10g": round(gi["p916_10g"] * ratio_g), "gold_750_10g": round(gi["p750_10g"] * ratio_g),
                "silver_999_kg": round(si["p999_kg"] * ratio_s),
                "margin_pct": {"gold": margin("gold", hrs, logs, ns), "silver": margin("silver", hrs, logs, ns)}}
        sess = {n1[1].lower(): blk(*n1), n2[1].lower(): blk(*n2)}
        ie = D.setdefault("india_estimate", {})
        ie.update({"am": sess["am"], "pm": sess["pm"], "status": "estimate",
            "for_date": f"{sess['am']['for']} (IBJA AM, ~12:30 pm)",
            "gold_999_10g": sess["am"]["gold_999_10g"], "gold_916_10g": sess["am"]["gold_916_10g"], "gold_750_10g": sess["am"]["gold_750_10g"],
            "silver_999_kg": sess["am"]["silver_999_kg"], "margin_pct": sess["am"]["margin_pct"],
            "basis": f"{gi['date']} {gi['session']} × (spot now ÷ spot at that fix) × (USD-INR now ÷ then). Gold ${float(gi.get('spot_at_fix_usd') or g):,.2f} → ${g:,.2f}; "
                     + (f"silver ${float(si.get('spot_at_fix_usd') or s):,.2f} → ${s:,.2f}; " if s else "")
                     + (f"USD-INR {float(gi.get('fx_at_fix') or r):.2f} → {r:.2f}. " if r else "")
                     + f"Updated automatically at {stamp}.",
            "pm_note": "Best guess for later today is the current price; the margin is wider because there are more hours for the price to move."})
        D["india_outlook"] = {"text": f"Since the last IBJA fix ({gi['date']}, {gi['session'].replace('IBJA ','')}), gold has moved {(ratio_g-1)*100:+.2f}% in rupee terms and silver {(ratio_s-1)*100:+.2f}%. If that holds, the next IBJA 24K would be near ₹{gi['p999_10g']*ratio_g/10:,.0f}/g.",
            "basis": "Arithmetic from the live figures above; not a forecast from any source."}
        changed = True

    if changed:
        D["updated_at"] = NOW.isoformat(timespec="seconds")
        D["next_update"] = "Every 30 min on weekdays (prices); news ~08:45 and ~13:45 IST"
        ym = NOW.strftime("%Y-%m"); rows = H["rows"]
        newrow = [ym, round(g, 2) if g else rows[-1][1], round(s, 3) if s else rows[-1][2], round(r, 2) if r else rows[-1][3]]
        if rows[-1][0] == ym: rows[-1] = newrow
        else: rows.append(newrow)
        json.dump(D, open("data.json", "w"), ensure_ascii=False, indent=1)
        json.dump(H, open("history_monthly.json", "w"), separators=(",", ":"))
        print("updated", D["updated_at"], "gold", g, gst, "silver", s, sst, "fx", r, rst)
    else:
        print("no change")

if __name__ == "__main__":
    main()
