"""End-to-end automated tests for PO receive_date validation + batch registration
+ stock-movement report filtering, plus the prescription-edit no-data-loss guard.

Run with:
    python manage.py shell < tests_e2e.py
Or install via Django test runner (script can also be imported).
"""

import os
import sys
import traceback
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmacy_project.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.messages import get_messages
from django.db import transaction

from pharmacy.models import (
    Medicine, Supplier, OrderHeader, OrderItem, Batch,
    Prescription, DispensingItem,
)
from pharmacy.forms import OrderHeaderForm
from pharmacy.views import (
    _validate_dispensing_items, _apply_dispensing_items, _restore_stock,
    _create_batch_and_update_stock, report_stock_movement,
)


class FakeRequest:
    """Minimal request-like object for calling _validate_dispensing_items / views helpers
    directly from tests without spinning up the full test client.
    """
    method = 'POST'

    def __init__(self, post=None, user=None):
        from django.http import QueryDict
        qd = QueryDict(mutable=True)
        if post:
            for k, v in post.items():
                if isinstance(v, (list, tuple)):
                    qd.setlist(k, list(v))
                else:
                    qd[k] = v
        self.POST = qd
        self.user = user
        self.session = {}
        self._messages = FallbackStorage(self)

    def getlist(self, key, default=None):
        return self.POST.getlist(key, default if default is not None else [])


def _make_user(username='testuser'):
    u, _ = User.objects.get_or_create(username=username, defaults={'is_staff': True, 'is_active': True})
    u.set_password('x')
    u.save()
    return u


def _make_supplier(name='Al-Watania Pharma'):
    return Supplier.objects.get_or_create(name=name, defaults={'phone': '0000000000'})[0]


def _make_medicine(name='Panadol Cold', unit='علبة', reorder_level=5, default_qty=1, category='OTC'):
    return Medicine.objects.get_or_create(
        name=name,
        defaults={'unit': unit, 'reorder_level': reorder_level,
                  'default_dispense_qty': default_qty, 'category': category}
    )[0]


# ---------------------------------------------------------------------------
# 1. PO Validation: Delivered status without receive_date MUST block save
# ---------------------------------------------------------------------------
def test_po_delivered_requires_receive_date():
    """PO (OrderHeader) with status='Delivered' AND receive_date=None
    must raise a clear ValidationError and must NOT hit the database."""
    supplier = _make_supplier()
    user = _make_user()

    # 1A — Model level: model.clean() must raise ValidationError
    order = OrderHeader(
        supplier=supplier,
        order_date=date.today(),
        status='Delivered',
        receive_date=None,  # INTENTIONALLY BLANK
        created_by=user,
        updated_by=user,
    )
    raised = False
    try:
        order.full_clean()  # triggers clean()
    except ValidationError as e:
        raised = True
        assert 'receive_date' in e.message_dict, (
            f'Expected receive_date key in ValidationError keys, got {e.message_dict}'
        )
        assert any('تاريخ الاستلام مطلوب' in m for m in e.message_dict['receive_date']), (
            f'Arabic error message missing in: {e.message_dict}'
        )
    assert raised, 'OrderHeader.clean() did not raise for missing receive_date + Delivered status'

    # 1B — Form level: OrderHeaderForm must invalidate with same field error
    data = {
        'supplier': supplier.pk,
        'order_date': date.today().isoformat(),
        'status': 'Delivered',
        'receive_date': '',   # BLANK — must fail
        'notes': '',
    }
    form = OrderHeaderForm(data=data)
    assert not form.is_valid(), (
        f'OrderHeaderForm must be invalid for Delivered + blank receive_date. errors: {form.errors}'
    )
    assert 'receive_date' in form.errors, (
        f'Expected receive_date in form errors: {form.errors}'
    )

    # 1C — Sanity check: same form but WITH receive_date VALIDATES
    data['receive_date'] = date.today().isoformat()
    form2 = OrderHeaderForm(data=data)
    if not form2.is_valid():
        print('  form2 errors:', form2.errors)
    assert form2.is_valid(), 'Valid Delivered PO (with receive_date) must pass form validation'

    # 1D — Pending status does NOT require receive_date
    data['status'] = 'Pending'
    data['receive_date'] = ''
    form3 = OrderHeaderForm(data=data)
    assert form3.is_valid(), 'Pending PO must be valid even without receive_date'

    print('  ✅ PO delivered-status receive_date validation PASS')


# ---------------------------------------------------------------------------
# 2. Batch.date_received must reflect PO effective_receive_date
# ---------------------------------------------------------------------------
def test_batch_uses_receive_date_on_registration():
    supplier = _make_supplier('Batch-Tester Co')
    user = _make_user('batchtester')
    med = _make_medicine('Amoxicillin 500mg BatchTest')

    receive = date(2026, 5, 15)
    order = OrderHeader.objects.create(
        supplier=supplier, order_date=date(2026, 5, 1),
        status='Delivered', receive_date=receive,
        created_by=user, updated_by=user,
    )

    item = OrderItem(
        order=order, medicine=med,
        quantity_ordered=100, quantity_received=100,
        unit_cost=Decimal('5.50'),
        batch_number='BT-2026-MAY',
        expiry_date=date(2027, 10, 1),
        created_by=user, updated_by=user,
    )
    item._skip_stock_signal = True   # prevent OrderItem signal double-counting
    item.save()
    _create_batch_and_update_stock(item, order)

    batch = Batch.objects.filter(batch_number='BT-2026-MAY', medicine=med).first()
    assert batch is not None, 'Batch was not created'
    assert batch.date_received == receive, (
        f'Batch date_received must equal PO.receive_date ({receive}), got {batch.date_received}'
    )
    assert batch.quantity_remaining == 100
    med.refresh_from_db()
    assert med.current_stock >= 100, 'Medicine stock must have been incremented'

    # 2B — Fallback: if receive_date is null (Pending POs still have items
    # processed with order_date), Batch.date_received should fall back to order_date
    order2 = OrderHeader.objects.create(
        supplier=supplier, order_date=date(2026, 3, 10),
        status='Pending', receive_date=None,
        created_by=user, updated_by=user,
    )
    item2 = OrderItem(
        order=order2, medicine=med,
        quantity_ordered=10, quantity_received=10,
        batch_number='BT-FALLBACK',
        expiry_date=date(2028, 1, 1),
        created_by=user, updated_by=user,
    )
    item2._skip_stock_signal = True
    item2.save()
    _create_batch_and_update_stock(item2, order2)
    batch2 = Batch.objects.get(batch_number='BT-FALLBACK', medicine=med)
    assert batch2.date_received == date(2026, 3, 10), (
        f'Batch fallback must use order_date 2026-03-10, got {batch2.date_received}'
    )
    print('  ✅ Batch.date_received derived correctly from PO effective_receive_date PASS')


# ---------------------------------------------------------------------------
# 3. Movement report must include "received" by receive_date bounds
# ---------------------------------------------------------------------------
def test_movement_report_filters_by_effective_receive_date():
    """Three POs, three different receive dates, verify correct counts
    appear in each report window.  Uses django.test.Client so the view
    response.context is populated like a real request.
    """
    from django.test import Client
    from django.test.utils import setup_test_environment
    setup_test_environment()  # Required for response.context to be populated

    supplier = _make_supplier('Movement-Report Co')
    user = _make_user('movementtester')
    med = _make_medicine('Vitamin C Movement')

    def make_po(pk_in_report, order_dt, receive_dt, qty=50, status='Delivered'):
        order = OrderHeader.objects.create(
            supplier=supplier, order_date=order_dt, status=status,
            receive_date=receive_dt,
            created_by=user, updated_by=user,
        )
        item = OrderItem(
            order=order, medicine=med,
            quantity_ordered=qty, quantity_received=qty,
            batch_number=f'MVT-{pk_in_report}', expiry_date=date(2029, 12, 1),
            created_by=user, updated_by=user,
        )
        item._skip_stock_signal = True
        item.save()
        _create_batch_and_update_stock(item, order)
        return order, item

    # PO A: receive_date = 2026-02-10  (BEFORE window 2026-04-01..2026-04-30)
    make_po('A', date(2026, 2, 1), date(2026, 2, 10), qty=3)
    # PO B: receive_date = 2026-04-15  (INSIDE window)
    make_po('B', date(2026, 3, 20), date(2026, 4, 15), qty=7)
    # PO C: receive_date = 2026-05-05  (AFTER window)
    make_po('C', date(2026, 4, 28), date(2026, 5, 5), qty=11)

    client = Client()
    # Client needs a logged-in admin user because @login_required_custom redirects
    User.objects.filter(pk=user.pk).update(is_superuser=True, is_staff=True)
    from django.contrib.auth.hashers import make_password
    User.objects.filter(pk=user.pk).update(password=make_password('welcome12345'))
    assert client.login(username=user.username, password='welcome12345'), (
        f'Unable to log client in as {user.username}'
    )

    from django.test.utils import override_settings

    # Stock movement view requires 'testserver' host OK; allow '*' for tests.
    with override_settings(ALLOWED_HOSTS=['*']):
        resp = client.get('/reports/stock-movement/',
                          {'from': '2026-04-01', 'to': '2026-04-30'})
        assert resp.status_code == 200, (
            f'Stock movement page returned {resp.status_code}'
        )
        rows = resp.context.get('rows')
        assert rows is not None, (
            'Template context "rows" missing — did the URL config change?'
        )
        mine = next((r for r in rows if r['medicine'].pk == med.pk), None)
        assert mine is not None, 'Vitamin C Movement must show up in report rows'
        # Only PO B (qty=7) should be "purchased" within April
        assert mine['purchased'] == 7, (
            f'Expected purchased=7 (only PO B in April window), '
            f'got {mine["purchased"]}'
        )

        # Check opening_stock: purchases_before (PO A qty=3) - dispensed_before (0) = 3
        assert mine['opening_stock'] == 3, (
            f'Expected opening_stock=3 (PO A before window), '
            f'got {mine["opening_stock"]}'
        )
        # Closing = 3 + 7 - 0 = 10
        assert mine['closing_stock'] == 10, (
            f'Expected closing_stock=10, got {mine["closing_stock"]}'
        )

        # Now query window 2026-05-01..2026-05-31: purchased should = 11 (PO C only)
        resp2 = client.get('/reports/stock-movement/',
                           {'from': '2026-05-01', 'to': '2026-05-31'})
        assert resp2.status_code == 200
        rows2 = resp2.context['rows']
        mine2 = next((r for r in rows2 if r['medicine'].pk == med.pk), None)
        assert mine2 is not None
        assert mine2['purchased'] == 11, (
            f'Expected purchased=11 for May window, got {mine2["purchased"]}'
        )
        assert mine2['opening_stock'] == 10, (
            f'Opening for May: 3+7 = 10; got {mine2["opening_stock"]}'
        )
    print('  ✅ Movement report correctly filters by effective receive_date PASS')


# ---------------------------------------------------------------------------
# 4. Prescription edit with invalid items MUST NOT destroy existing items
# ---------------------------------------------------------------------------
def test_prescription_edit_validation_preserves_existing_items():
    user = _make_user('presetester')
    supplier = _make_supplier('Rx supplier')
    med = _make_medicine('Augmentin 625mg PresEdit')
    # First build stock via PO
    order = OrderHeader.objects.create(
        supplier=supplier, order_date=date.today(),
        status='Delivered', receive_date=date.today(),
        created_by=user, updated_by=user,
    )
    item = OrderItem(
        order=order, medicine=med,
        quantity_ordered=50, quantity_received=50,
        batch_number='RX-AUG-BATCH', expiry_date=date(2028, 6, 1),
        created_by=user, updated_by=user,
    )
    item._skip_stock_signal = True
    item.save()
    _create_batch_and_update_stock(item, order)
    batch = Batch.objects.get(batch_number='RX-AUG-BATCH', medicine=med)
    med.refresh_from_db()

    # Create a valid prescription dispensing qty=20
    rx = Prescription.objects.create(
        prescription_ref='PRX001', dispensing_date=date.today(),
        created_by=user, updated_by=user,
    )
    DispensingItem.objects.create(
        prescription=rx, medicine=med, batch=batch,
        quantity_dispensed=20,
        created_by=user, updated_by=user,
    )
    batch.refresh_from_db()
    med.refresh_from_db()
    assert batch.quantity_remaining == 30, (
        f'Staging check failed: batch remaining should be 50-20=30, got {batch.quantity_remaining}'
    )
    assert med.current_stock == 30, (
        f'Staging check failed: med stock should be 30, got {med.current_stock}'
    )
    assert rx.items.count() == 1

    # Now simulate an EDIT POST that tries to bump qty to 500 (impossible — exceeds remaining)
    post = {
        'item_medicine[]': [str(med.pk)],
        'item_batch[]': [str(batch.pk)],
        'item_quantity[]': ['500'],   # EXCEEDS available (30 + restored 20 = 50 still < 500!)
    }
    req = FakeRequest(post=post, user=user)
    snapshot = list(rx.items.select_related('medicine', 'batch').all())
    _parsed, errors = _validate_dispensing_items(req, prescription_snapshot=snapshot)
    assert len(errors) > 0, f'Expected validation error for qty 500, got none'
    # CRITICAL CHECK: existing dispensing items must still exist untouched
    assert rx.items.count() == 1, (
        f'Existing dispensing items were DELETED despite validation failing! count={rx.items.count()}'
    )
    original_item = rx.items.first()
    assert original_item.quantity_dispensed == 20, (
        f'Original dispensing qty was modified! Expected 20, got {original_item.quantity_dispensed}'
    )
    batch.refresh_from_db()
    med.refresh_from_db()
    assert batch.quantity_remaining == 30, (
        f'Batch remaining changed during failed validation! Expected 30, got {batch.quantity_remaining}'
    )
    assert med.current_stock == 30, (
        f'Medicine stock changed! Expected 30, got {med.current_stock}'
    )
    print('  ✅ Prescription edit validation never destroys existing items PASS')


# ---------------------------------------------------------------------------
RUNNERS = [
    ('PO#1 validation (Delivered needs receive_date)',    test_po_delivered_requires_receive_date),
    ('PO#2 batch.date_received from effective receive_date', test_batch_uses_receive_date_on_registration),
    ('PO#3 movement report filters by effective date',    test_movement_report_filters_by_effective_receive_date),
    ('Presc-edit no-data-loss guard',                     test_prescription_edit_validation_preserves_existing_items),
]


def run():
    print('\n=== E2E Automated Tests ===\n')
    passed = failed = 0
    for name, fn in RUNNERS:
        print(f'[ RUN ]  {name}')
        try:
            with transaction.atomic():
                fn()
                # Roll back so tests are idempotent
                transaction.set_rollback(True)
            passed += 1
        except Exception:
            failed += 1
            traceback.print_exc()
            print(f'[ FAIL ] {name}\n')
    print(f'\n=== Result: {passed} passed, {failed} failed of {len(RUNNERS)} total ===\n')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    # Force UTF-8 for Windows terminals so Arabic+emoji print fine
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') != 'utf8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    sys.exit(run())
