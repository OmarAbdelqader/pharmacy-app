# Local Network Validation

Run these steps from the project directory in PowerShell.

## 1. Prepare the environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
```

Create an administrator if the database does not already have one:

```powershell
python manage.py createsuperuser
```

## 2. Run automated checks

```powershell
python manage.py check
python manage.py test
```

Both commands should complete without errors. The test suite should report all tests as `OK`.

## 3. Start the LAN server

Find the host computer's IPv4 address:

```powershell
ipconfig
```

Start Django on every network interface:

```powershell
python manage.py runserver 0.0.0.0:8000
```

On the host computer, open `http://127.0.0.1:8000/`. From another device on the same network, open `http://<HOST_IPV4>:8000/`, for example `http://192.168.1.13:8000/`.

If another device cannot connect, allow Python through the Windows Firewall for private networks and confirm both devices are on the same network.

## 4. Functional smoke test

1. Log in with the administrator account.
2. Open the dashboard and confirm the inventory counters load.
3. Create a medicine, supplier, and medicine code.
4. Create a purchase order with a received quantity and batch expiry date.
5. Confirm current stock and the current-stock report include the received batch.
6. Create a prescription using the medicine code and batch.
7. Confirm stock decreases and the daily dispensing report shows the prescription.
8. Edit the prescription and verify stock is restored and re-applied exactly once.
9. Open low-stock, expiry, under-supply, and stock-movement reports.
10. Log out, then confirm protected pages redirect to the login page.

## 5. Performance regression check

Run the focused test after changes to list views, reports, or stock processing:

```powershell
python manage.py test pharmacy.tests
```

The medicine JSON regression test should pass. For a larger-data check, load at least 100 medicines with codes and batches, open the prescription form, and confirm it remains responsive. Repeat the list and report pages while watching the Django console for errors.

## 6. Data safety

Before testing destructive actions, copy `db.sqlite3` to a backup. After testing, verify that medicine stock equals received quantities minus dispensed quantities and that no batch has negative remaining quantity.
