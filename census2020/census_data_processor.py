import dask.dataframe as dd
import os

RACE_MAPPING = {
    'hpi': 'Hawaiian Pacific Islander',
    'a': 'Asian',
    'm': 'Mixed',
    'o': 'Hispanic or Other',
    'b': 'Black',
    'n': 'Native American',
    'w': 'White'
}

def read_and_clean_data(file_path, mapping=RACE_MAPPING) -> dd.DataFrame:
    """
    Reads, cleans and processes the census data.
    
    Parameters:
        file_path (str): Path to the Parquet file.
        race_mapping (dict): Mapping from race codes to descriptive names.

    Returns:
        dd.DataFrame: The cleaned and processed Dask DataFrame.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    
    df = dd.read_parquet(file_path)
    df = df.reset_index(drop=True).rename(columns={'R': 'race'})    

    df['race'] = df['race'].astype('category')
    df['race'] = df['race'].cat.rename_categories(mapping)
    
    return df.persist()

def load_data(file_path: str) -> dd.DataFrame:
    """
    Loads and cleans the census data from a Parquet file.
    
    Parameters:
        file_path (str): Path to the Parquet file.        
    Returns:
        dd.DataFrame: The cleaned and processed Dask DataFrame.
    """
    return read_and_clean_data(file_path)
