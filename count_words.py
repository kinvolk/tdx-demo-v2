import polars as pl
import crypto
from os import environ

# Get symmetric key from the environment
key = environ["KEY"]

# Decrypt the encrypted dataframe
df_enc = pl.read_csv("df_enc.csv")
df = (df_enc.lazy().select(
    pl.col('secret').apply(lambda v: crypto.decrypt_val(key, v)),
))

# Count all the secret words
count = df.select(
    pl.col('secret').apply(lambda v: len(v.split(" ")))
).sum().collect()
print(count)
