from datetime import date

from django.contrib.auth.models import User
from django.forms import formset_factory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import OrderHeaderForm, OrderItemForm
from .models import (
    Batch, Medicine, MedicineCode, OrderHeader, OrderItem, Supplier,
    InternalDispensing, InternalDispensingItem,
)
from .views import _get_medicines_json, _save_order_items


class OrderItemSaveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='testpass')
        self.supplier = Supplier.objects.create(name='Supplier One')
        self.medicine = Medicine.objects.create(name='Paracetamol', current_stock=0)
        self.order = OrderHeader.objects.create(
            supplier=self.supplier,
            order_date=timezone.now().date(),
            status='Delivered',
            receive_date=timezone.now().date(),
            created_by=self.user,
            updated_by=self.user,
        )

    def test_order_form_renders_clickable_delete_control(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('order_add'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'for="id_items-0-DELETE"')
        self.assertContains(response, 'name="items-0-DELETE"')

    def test_save_order_items_creates_items_and_batches(self):
        formset_class = formset_factory(OrderItemForm, extra=0)
        data = {
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-0-medicine': str(self.medicine.pk),
            'items-0-quantity_ordered': '10',
            'items-0-quantity_received': '5',
            'items-0-unit_cost': '2.50',
            'items-0-batch_number': 'B-001',
            'items-0-expiry_date': '2030-01',
        }

        formset = formset_class(data=data, prefix='items')

        self.assertTrue(formset.is_valid(), formset.errors)

        item_count = _save_order_items(self.order, formset)

        self.assertEqual(item_count, 1)
        self.assertEqual(self.order.items.count(), 1)
        item = self.order.items.get()
        self.assertEqual(item.medicine, self.medicine)
        self.assertEqual(item.quantity_received, 5)
        self.assertTrue(Batch.objects.filter(medicine=self.medicine, batch_number='B-001').exists())
        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.current_stock, 5)

    def test_pending_order_does_not_update_stock(self):
        self.order.status = 'Pending'
        self.order.receive_date = None
        self.order.save()
        formset_class = formset_factory(OrderItemForm, extra=0)
        formset = formset_class(data={
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-0-medicine': str(self.medicine.pk),
            'items-0-quantity_ordered': '10',
            'items-0-quantity_received': '5',
            'items-0-batch_number': 'PENDING-001',
            'items-0-expiry_date': '2030-01',
        }, prefix='items')

        self.assertTrue(formset.is_valid(), formset.errors)
        _save_order_items(self.order, formset)

        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.current_stock, 0)
        self.assertFalse(Batch.objects.filter(batch_number='PENDING-001').exists())

    def test_pending_order_item_signal_does_not_update_stock(self):
        self.order.status = 'Pending'
        self.order.receive_date = None
        self.order.save()
        OrderItem.objects.create(
            order=self.order,
            medicine=self.medicine,
            quantity_ordered=10,
            quantity_received=5,
            batch_number='PENDING-SIGNAL',
            expiry_date='2030-01-01',
        )

        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.current_stock, 0)
        self.assertFalse(Batch.objects.filter(batch_number='PENDING-SIGNAL').exists())

    def test_delivered_form_requires_actual_receive_date(self):
        form = OrderHeaderForm(data={
            'supplier': self.supplier.pk,
            'order_date': '2026-09-01',
            'receive_date': '2026-09-03',
            'status': 'Delivered',
            'received_by': '',
            'supplier_reference': '',
            'notes': '',
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(str(form.cleaned_data['receive_date']), '2026-09-03')

    def test_failed_login_does_not_reach_dashboard(self):
        response = self.client.post(reverse('login'), {
            'username': self.user.username,
            'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['login_error'])
        self.assertContains(response, 'اسم المستخدم أو كلمة المرور غير صحيحة')

        response = self.client.post(reverse('login'), {
            'username': self.user.username,
            'password': 'testpass',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'اسم المستخدم أو كلمة المرور غير صحيحة')

    def test_medicine_json_uses_constant_query_count(self):
        MedicineCode.objects.create(medicine=self.medicine, code='PAR-001')
        Batch.objects.create(
            medicine=self.medicine,
            batch_number='B-001',
            expiry_date=timezone.now().date(),
            quantity_received=5,
            quantity_remaining=5,
        )

        with self.assertNumQueries(3):
            payload = _get_medicines_json()

        self.assertIn('PAR-001', payload)


class StockMovementReportTests(TestCase):
    def test_report_uses_effective_receive_date_without_per_medicine_queries(self):
        user = User.objects.create_user(username='reporter', password='testpass')
        supplier = Supplier.objects.create(name='Report Supplier')
        medicine = Medicine.objects.create(name='Report Medicine')

        for order_date, receive_date, quantity in (
            (date(2026, 2, 1), date(2026, 2, 10), 3),
            (date(2026, 3, 20), date(2026, 4, 15), 7),
            (date(2026, 4, 28), date(2026, 5, 5), 11),
        ):
            order = OrderHeader.objects.create(
                supplier=supplier,
                order_date=order_date,
                receive_date=receive_date,
                status='Delivered',
                created_by=user,
                updated_by=user,
            )
            OrderItem.objects.create(
                order=order,
                medicine=medicine,
                quantity_ordered=quantity,
                quantity_received=quantity,
                batch_number=f'B-{quantity}',
                expiry_date=date(2029, 12, 1),
                created_by=user,
                updated_by=user,
            )

        self.client.force_login(user)
        response = self.client.get(
            '/reports/stock-movement/',
            {'from': '2026-04-01', 'to': '2026-04-30'},
        )

        self.assertEqual(response.status_code, 200)
        row = response.context['rows'][0]
        self.assertEqual(row['purchased'], 7)
        self.assertEqual(row['opening_stock'], 3)
        self.assertEqual(row['closing_stock'], 10)


class InternalDispensingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='internal-user', password='testpass')
        self.source = Medicine.objects.create(name='Source medicine', current_stock=0)
        self.destination = Medicine.objects.create(name='Receiving medicine', current_stock=0)
        self.batch = Batch.objects.create(
            medicine=self.source,
            batch_number='TRANSFER-01',
            expiry_date=date(2030, 6, 30),
            quantity_received=12,
            quantity_remaining=12,
        )
        self.client.force_login(self.user)

    def transfer_data(self, quantity=5, destination_type='internal'):
        return {
            'dispensing_date': '2026-09-06',
            'destination_type': destination_type,
            'destination_name': 'Ward A',
            'destination_medicine': self.destination.pk if destination_type == 'internal' else '',
            'notes': '',
            'item_medicine[]': str(self.source.pk),
            'item_batch[]': str(self.batch.pk),
            'item_destination_medicine[]': str(self.destination.pk) if destination_type == 'internal' else '',
            'item_quantity[]': str(quantity),
        }

    def test_internal_transfer_moves_stock_with_batch_metadata(self):
        response = self.client.post('/internal-dispensing/add/', self.transfer_data())

        self.assertRedirects(response, '/internal-dispensing/')
        self.batch.refresh_from_db()
        self.source.refresh_from_db()
        self.destination.refresh_from_db()
        received_batch = Batch.objects.get(medicine=self.destination)
        self.assertEqual(self.batch.quantity_remaining, 7)
        self.assertEqual(self.source.current_stock, 7)
        self.assertEqual(received_batch.batch_number, self.batch.batch_number)
        self.assertEqual(received_batch.expiry_date, self.batch.expiry_date)
        self.assertEqual(received_batch.quantity_remaining, 5)
        self.assertEqual(self.destination.current_stock, 5)
        self.assertEqual(InternalDispensingItem.objects.count(), 1)

    def test_external_transfer_only_consumes_source_stock(self):
        response = self.client.post(
            '/internal-dispensing/add/',
            self.transfer_data(destination_type='external'),
        )

        self.assertRedirects(response, '/internal-dispensing/')
        self.batch.refresh_from_db()
        self.source.refresh_from_db()
        self.destination.refresh_from_db()
        self.assertEqual(self.batch.quantity_remaining, 7)
        self.assertEqual(self.source.current_stock, 7)
        self.assertEqual(self.destination.current_stock, 0)
        self.assertFalse(Batch.objects.filter(medicine=self.destination).exists())

    def test_excess_quantity_does_not_create_transfer_or_change_stock(self):
        response = self.client.post('/internal-dispensing/add/', self.transfer_data(quantity=13))

        self.assertEqual(response.status_code, 200)
        self.batch.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual(self.batch.quantity_remaining, 12)
        self.assertEqual(self.source.current_stock, 12)
        self.assertEqual(InternalDispensing.objects.count(), 0)
        self.assertEqual(InternalDispensingItem.objects.count(), 0)

    def test_edit_replaces_lines_and_restores_both_sides(self):
        self.client.post('/internal-dispensing/add/', self.transfer_data(quantity=5))
        dispensing = InternalDispensing.objects.get()
        response = self.client.post(
            f'/internal-dispensing/{dispensing.pk}/edit/',
            self.transfer_data(quantity=3, destination_type='external'),
        )

        self.assertRedirects(response, '/internal-dispensing/')
        self.batch.refresh_from_db()
        self.source.refresh_from_db()
        self.destination.refresh_from_db()
        self.assertEqual(self.batch.quantity_remaining, 9)
        self.assertEqual(self.source.current_stock, 9)
        self.assertEqual(self.destination.current_stock, 0)
        self.assertIsNone(dispensing.items.get().destination_medicine_id)

    def test_internal_transfer_is_visible_in_stock_movement_report(self):
        self.client.post('/internal-dispensing/add/', self.transfer_data(quantity=5))

        response = self.client.get('/reports/stock-movement/', {
            'from': '2026-09-01',
            'to': '2026-09-06',
        })

        rows = {row['medicine'].pk: row for row in response.context['rows']}
        self.assertEqual(rows[self.source.pk]['dispensed'], 5)
        self.assertEqual(rows[self.destination.pk]['purchased'], 5)

    def test_external_transfer_is_visible_as_dispensed(self):
        self.client.post(
            '/internal-dispensing/add/',
            self.transfer_data(quantity=5, destination_type='external'),
        )

        response = self.client.get('/reports/stock-movement/', {
            'from': '2026-09-01',
            'to': '2026-09-06',
        })

        rows = {row['medicine'].pk: row for row in response.context['rows']}
        self.assertEqual(rows[self.source.pk]['dispensed'], 5)
        self.assertNotIn(self.destination.pk, rows)
