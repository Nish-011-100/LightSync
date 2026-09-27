# Observation log

Use the Observation log tab for new real field checks. Local storage: data/field_logs/observations.sqlite3 (Git-ignored); explicitly export reviewed records to share. The original 20 intervals remain unchanged. Empty storage contains no sample or synthetic observations.

Schema: record_id UUID; recorded_at_utc audit time; observed_at_ist actual check time (+05:30); location_id inventory foreign key; observer_alias pseudonym; light_state ON/OFF/Partly ON/Unable to determine; check_interval_minutes nullable integer (unknown is null); count_basis distinguishes not recorded, physically counted and estimated; installed_count and nonworking_count nullable integers; lux nullable nonnegative measurement; lux_method distinguishes none, meter and uncalibrated phone; notes free text.

The form rejects future timestamps, missing aliases and invalid count relationships. Entries are append-only. A partly illuminated zone does not establish an exact faulty count. Use notes to document transition brackets; a check is not a switching interval. Do not enter identifiable personal data. Local storage is not an authenticated multi-user production database. Exports escape spreadsheet formula prefixes in notes/aliases.
