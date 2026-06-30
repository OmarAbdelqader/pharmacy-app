from django.contrib.auth.models import User
from django.forms import formset_factory
from django.test import TestCase
from django.utils import timezone

from .forms import OrderItemForm
from .models import Batch, Medicine, OrderHeader, Supplier
from .views import _save_order_items


class OrderItemSaveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='testpass')
        self.supplier = Supplier.objects.create(name='Supplier One')
        self.medicine = Medicine.objects.create(name='Paracetamol', current_stock=0)
        self.order = OrderHeader.objects.create(
            supplier=self.supplier,
            order_date=timezone.now().date(),
            created_by=self.user,
            updated_by=self.user,
        )

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
