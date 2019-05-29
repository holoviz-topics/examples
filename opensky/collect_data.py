"""
Run a cron job with the following script running at one-minute intervals
over a four-day period to collect the data used in the notebook.
"""

import json, sqlite3, requests, pandas as pd

DB='./data/opensky.db'
conn = sqlite3.connect(DB)
api_url = 'https://opensky-network.org/api/states/all'

cols = ['icao24', 'callsign', 'origin', 'time_position', 'time_velocity',
        'longitude', 'latitude', 'altitude', 'on_ground', 'velocity',
        'heading', 'vertical_rate', 'sensors']

req = requests.get(api_url)
content = json.loads(req.content)
states = content['states']
df = pd.DataFrame(states, columns=cols)
df['timestamp'] = content['time']
df.to_sql('opensky', conn, index=False, if_exists='append')
