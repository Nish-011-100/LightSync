"""Check delivered notebook execution and record the tested package versions."""
import importlib.metadata
import json
from pathlib import Path
import nbformat

root=Path(__file__).resolve().parents[1]
results=[]
for name in ['01_Data_Preparation.ipynb','02_Model_Training.ipynb','03_Lighting_and_Energy.ipynb']:
    notebook=nbformat.read(root/name,as_version=4)
    nbformat.validate(notebook)
    cells=[c for c in notebook.cells if c.cell_type=='code']
    record={'notebook':name,'code_cells':len(cells),
            'unexecuted':sum(c.execution_count is None for c in cells),
            'errors':sum(o.output_type=='error' for c in cells for o in c.outputs)}
    assert record['unexecuted']==0 and record['errors']==0, record
    results.append(record)
(root/'reports/notebook_execution_check.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
versions={name:importlib.metadata.version(name) for name in
          ['pandas','numpy','scikit-learn','joblib','pyarrow','astral','matplotlib','streamlit','nbformat','nbclient']}
(root/'reports/tested_package_versions.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
print('All notebook cells executed without errors.')
