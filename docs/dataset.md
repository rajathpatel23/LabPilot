Dataset Guide

Goal

This document lists the datasets LabPilot should prioritize for the MVP, why they matter, and the fastest ways to download and start using them.

The guiding rule is simple: use a real-world reaction optimization dataset with a clear target like yield. Do not start with a generic chemistry corpus.

Priority order

1. Suzuki–Miyaura HTE dataset

Best first choice for the MVP.

Why:
	•	strong fit for experiment recommendation
	•	structured reaction conditions + yield
	•	widely used in reaction-yield modeling benchmarks
	•	manageable size for a hackathon

Use this if you want the cleanest “next best experiment” story.

Fastest download path:

mkdir -p data/Suzuki-Miyaura
curl -L "https://raw.githubusercontent.com/rxn4chemistry/rxn_yields/master/data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx" \
  -o data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx

Quick load test:

import pandas as pd

path = "data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx"
df = pd.read_excel(path)
print(df.head())
print(df.columns.tolist())
print(df.shape)

2. Buchwald–Hartwig HTE dataset

Best fallback if Suzuki is inconvenient.

Why:
	•	also widely used for reaction-yield prediction
	•	structured and benchmark-friendly
	•	good fit for a tabular surrogate model

Fastest download path:

mkdir -p data/Buchwald-Hartwig
curl -L "https://raw.githubusercontent.com/rxn4chemistry/rxn_yields/master/data/Buchwald-Hartwig/Dreher_and_Doyle_input_data.xlsx" \
  -o data/Buchwald-Hartwig/Dreher_and_Doyle_input_data.xlsx

Quick load test:

import pandas as pd

path = "data/Buchwald-Hartwig/Dreher_and_Doyle_input_data.xlsx"
df = pd.read_excel(path)
print(df.head())
print(df.columns.tolist())
print(df.shape)

3. Open Reaction Database (ORD)

Best for long-term credibility, but heavier for MVP.

Why:
	•	official open reaction infrastructure
	•	broader than a single benchmark
	•	useful for future product expansion

Use ORD if:
	•	someone on the team can move fast with its format
	•	you want a stronger long-term data story
	•	you do not need the cleanest same-day benchmark

Fastest download path:

git lfs install
git clone https://github.com/open-reaction-database/ord-data.git data/ord-data

Useful links:

ORD docs:
https://docs.open-reaction-database.org/en/latest/overview.html

ORD data repo:
https://github.com/open-reaction-database/ord-data

Recommended decision

For the hackathon, start with:
	1.	Suzuki–Miyaura
	2.	Buchwald–Hartwig if Suzuki is annoying
	3.	ORD only if the team already knows how to use it

What to inspect immediately after download

Once the file is downloaded, inspect:
	•	column names
	•	target column (yield)
	•	number of rows
	•	categorical vs numeric columns
	•	missing values
	•	whether conditions are directly usable as features

Use this script first:

import pandas as pd

path = "data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx"  # swap as needed

df = pd.read_excel(path)

print("shape:", df.shape)
print("columns:")
for c in df.columns:
    print(" -", c)

print("\nnull counts:")
print(df.isnull().sum().sort_values(ascending=False).head(20))

print("\ndtypes:")
print(df.dtypes)

How to choose the first dataset fast

Choose the dataset that satisfies these conditions:
	•	easy to load in under 10 minutes
	•	clear yield-like target
	•	enough controllable condition columns
	•	minimal wrangling to get to a baseline model

If two datasets are available, choose the one with the cleaner schema, not the one that sounds more scientific.

Recommendation for LabPilot MVP

Use Suzuki first. If there is any friction, switch immediately to Buchwald–Hartwig and keep moving.

The main objective is not perfect chemistry coverage. The main objective is to get the surrogate model + optimizer loop working on real data as fast as possible.