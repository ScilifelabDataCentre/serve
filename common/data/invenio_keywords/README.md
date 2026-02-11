# Invenio keywords

This folder `common/data/invenio_keywords` contains pickled data use for autocomplete and term lookup. There are 2 types of files:

## "_autocomplete" file structure

This is a `dict` of `lists` file.

* keys are prefixes (2+ characters), values are term arrays
* each term has a relevance score based on prefix length
* minimal data for autocomplete

```Python
{
  "ca": [
    {'id': 'D002415', 'label': 'Cats', 'source': 'mesh', 'score': 4},
    {'id': 'D002420', 'label': 'Cardiac', 'source': 'mesh', 'score': 5},
    # ... more terms starting with "ca"
  ],
  "cal": [
    {'id': 'D031081', 'label': 'Calamus', 'source': 'mesh', 'score': 7},
    # ... more terms starting with "cal"  
  ],
  # ... other prefixes
}
```


## "_terms" file structure

These files include full term information to be used with Invenio records.

```Python
{
  "D000001": {
    'subject': 'Calcimycin',
    'subject_scheme': 'Medical Subject Headings', 
    'scheme_uri': 'https://meshb.nlm.nih.gov/',
    'value_uri': 'https://id.nlm.nih.gov/mesh/D000001',
    'classification_code': 'D000001',
    'lang': 'en'
  },
  # ... other terms with full metadata
}
```
