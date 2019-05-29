"""
Transform the opensky.db file collected using collect_data.py into Web Mercator
coordinates, split per flight, and export to Parquet format.

This process takes about 7 minutes on a MacBook Pro laptop.
"""

import sqlite3, pandas as pd, numpy as np, holoviews as hv, datashader.utils as du

def transform_coords(df):
    df=df.copy()
    df.loc[:, 'longitude'], df.loc[:, 'latitude'] = \
        du.lnglat_to_meters(df.longitude,df.latitude)
    return df

def split_flights(df):
    df = df.copy().reset_index(drop=True)
    df = df[np.logical_not(df.time_position.isnull())]
    empty=df[:1].copy()
    empty.loc[0, :] = 0
    empty.loc[0, 'origin'] = ''
    empty.loc[0, 'latitude'] = np.NaN
    empty.loc[0, 'longitude'] = np.NaN
    paths = []
    for gid, group in df.groupby('icao24'):
        times = group.time_position
        splits = np.split(group.reset_index(drop=True), np.where(times.diff()>600)[0])
        for split_df in splits:
            if len(split_df) > 20:
                paths += [split_df, empty]
    split = pd.concat(paths,ignore_index=True)
    split['ascending'] = split.vertical_rate>0
    return split

# Load the data from a SQLite database and project into Web Mercator (1.5 min)
DB='./data/opensky.db'
conn = sqlite3.connect(DB)
df = transform_coords(pd.read_sql("SELECT * from flights", conn))

# Split into groups by flight (6 min)
flightpaths = split_flights(df)

# Remove unused columns and declare categoricals
flightpaths = flightpaths[['longitude', 'latitude', 'origin', 'ascending', 'velocity']]
flightpaths['origin']    = flightpaths.origin.astype('category')
flightpaths['ascending'] = flightpaths.ascending.astype('bool')

# Export to Parquet
args = dict(engine="fastparquet", compression="snappy", has_nulls=False, write_index=False)
flightpaths.to_parquet("./data/opensky.parq", **args)
