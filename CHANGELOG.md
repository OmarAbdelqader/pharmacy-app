# Changelog

## [Unreleased]

### fix-medicines-page
- Fixed pagination controls on list pages so `previous_page_number` and `next_page_number` are resolved only when valid.
- Corrected medicine category filtering logic on the medicines list page.
- Added `متوسط الصنف` column to the expiry report.

### local-network
- Updated Django `ALLOWED_HOSTS` to allow local access from `192.168.1.13` and `pharmacy.local` for network testing.

### main
- Updated report templates with new Arabic labels and computed totals.
- Implemented under-supply report behavior and date formatting changes.
- Added user management views and report pages.
- Standardized expiry display formatting across reports and prescription batch selection.
