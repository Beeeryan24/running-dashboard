"""Pulls new runs and walks from Strava and merges them into runs.json / walks.json.
Existing entries are never overwritten, so your manual edits are kept."""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta

MN = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
RUN_TYPES = {'Run', 'TrailRun', 'VirtualRun'}
WALK_TYPES = {'Walk', 'Hike'}


def http(url, data=None, token=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None)
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def get_token():
    j = http('https://www.strava.com/oauth/token', {
        'client_id': os.environ['STRAVA_CLIENT_ID'],
        'client_secret': os.environ['STRAVA_CLIENT_SECRET'],
        'refresh_token': os.environ['STRAVA_REFRESH_TOKEN'],
        'grant_type': 'refresh_token'})
    return j['access_token']


def make(a, kcal):
    d = a['start_date_local'][:10]
    t = a['start_date_local'][11:16]
    y, m, dd = d.split('-')
    mi = a['distance'] / 1609.344
    mins = a['moving_time'] / 60
    if mi <= 0 or mins <= 0:
        return None
    cad = a.get('average_cadence')
    temp = a.get('average_temp')
    kcal = round(kcal, 1) if kcal else 0
    return {
        'date': d, 'time': t, 'label': f"{MN[int(m)-1]} {dd} '{y[2:]}",
        'duration_min': round(mins, 1), 'active_energy': kcal,
        'intensity': round(kcal / (mins / 60) / 61.2, 3) if kcal else 0,
        'max_hr': round(a['max_heartrate']) if a.get('max_heartrate') else None,
        'avg_hr': round(a['average_heartrate'], 1) if a.get('average_heartrate') else None,
        'distance': round(mi, 3), 'avg_speed': round(mi / (mins / 60), 3), 'pace': round(mins / mi, 2),
        'elevation_asc': round((a.get('total_elevation_gain') or 0) * 3.28084, 1),
        'cadence': round(cad * 2, 1) if cad else None,
        'temp': round(temp * 9 / 5 + 32) if temp is not None else None,
        'humidity': None,
    }


def exists(rows, new):
    for r in rows:
        if r['date'] != new['date']:
            continue
        if r.get('time') and r['time'] == new['time']:
            return True
        if abs(r['distance'] - new['distance']) < 0.2:
            return True
    return False


def merge(path, new_rows):
    rows = json.load(open(path)) if os.path.exists(path) else []
    added = 0
    for n in new_rows:
        if not exists(rows, n):
            rows.append(n); added += 1
    rows.sort(key=lambda r: (r['date'], r.get('time') or ''))
    if added:
        json.dump(rows, open(path, 'w'), separators=(',', ':'))
    return added, len(rows)


def fetch(token, days):
    after = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    out, page = [], 1
    while page <= 20:
        j = http(f'https://www.strava.com/api/v3/athlete/activities?per_page=100&page={page}&after={after}', token=token)
        if not j:
            break
        out += j; page += 1
    return out


def main(fetch_fn=fetch, detail_fn=None, token_fn=get_token, folder='.'):
    days = int(os.environ.get('DAYS') or 30)
    token = token_fn()
    acts = fetch_fn(token, days)
    detail = detail_fn or (lambda t, i: http(f'https://www.strava.com/api/v3/activities/{i}', token=t))
    runs, walks = [], []
    for a in acts:
        st = a.get('sport_type') or a.get('type')
        if st in RUN_TYPES:
            bucket = runs
        elif st in WALK_TYPES and not a.get('trainer'):
            bucket = walks
        else:
            continue
        try:
            kcal = detail(token, a['id']).get('calories')
        except Exception:
            kcal = None
        if not kcal and a.get('kilojoules'):
            kcal = a['kilojoules'] / 4.184
        r = make(a, kcal)
        if r:
            bucket.append(r)
    ra, rn = merge(os.path.join(folder, 'runs.json'), runs)
    wa, wn = merge(os.path.join(folder, 'walks.json'), walks)
    print(f'Strava activities checked: {len(acts)}. New runs: {ra} (total {rn}). New walks: {wa} (total {wn}).')


if __name__ == '__main__':
    main()
