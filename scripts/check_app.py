"""Exercise the dashboard without opening a browser."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

root=Path(__file__).resolve().parents[1]
app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
assert len(app.exception)==0, str(app.exception)
next(w for w in app.selectbox if w.label=='Location').select('Lohit Hostel')
next(w for w in app.selectbox if w.label=='Daylight scenario').select('lower_daylight')
app.checkbox[0].check()
app.run(timeout=30)
assert len(app.exception)==0, str(app.exception)
net=[m for m in app.metric if m.label=='Net energy saving'][0]
assert float(net.value.split()[0]) < 0, 'Lower-daylight corridor case should show extra energy, not hide it.'
assert any('illustrative' in c.value for c in app.caption)
next(r for r in app.radio if r.label=='Working-light count').set_value('max')
next(w for w in app.date_input if w.label=='Night starting').set_value(__import__('datetime').date(2026,9,26))
app.run(timeout=30)
assert len(app.exception)==0, str(app.exception)
print('Dashboard default, corridor, scenario, rates, count and night checks passed.')

next(w for w in app.button if w.label=='Generate my lighting plan').click()
app.run(timeout=30)
assert not app.exception, str(app.exception)
assert any(m.label=='Your net saving' for m in app.metric)
next(w for w in app.number_input if w.label=='Non-working lights').set_value(31)
next(w for w in app.button if w.label=='Generate my lighting plan').click()
app.run(timeout=30)
assert not app.exception
assert any('do not exceed' in e.value for e in app.error)
print('Custom plan submission and invalid count checks passed.')

next(w for w in app.date_input if w.label=='Night starting').set_value(__import__('datetime').date(2027,6,21))
app.run(timeout=60)
assert not app.exception, str(app.exception)
assert any('Selected-date ML prediction' in x.value for x in app.info)
print('Future date prediction passed.')
