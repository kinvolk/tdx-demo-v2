import polars as pl
import numpy as np
import crypto

# create a dataframe with some sensitive data
df = pl.DataFrame({
    "name": ["Jane Doe", "Joe Kerfuffle", "Peter Shaw", "Bob Andrews"],
    "secret": ["lorem ipsum", "dolor", "sit amet", "consectetur"],
})
print(df)

# encrypt the sensitive data
key = crypto.new_key()
df_enc = (df.lazy().select([
    pl.exclude('secret'),
    pl.col('secret').apply(lambda v: crypto.encrypt_val(key, v)),
])).collect()
print(df_enc)

# save the key and the encrypted data
with open("df_enc.key", "wb") as f: f.write(key)
with open("df_enc.csv", "w") as f: df_enc.write_csv(f)
