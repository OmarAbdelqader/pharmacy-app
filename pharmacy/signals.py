from django.db.models.signals import post_save, post_delete, pre_delete, pre_save
from django.dispatch import receiver
from django.db import models, transaction
from django.contrib.auth.models import User
from .models import UserProfile, Batch, DispensingItem, OrderItem, Medicine, Prescription
from .stock_history import record_stock_movement


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

@receiver(post_save, sender=User)
def sync_profile_role(sender, instance, created, **kwargs):
    try:
        profile = instance.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=instance)

    # Keep the stored role aligned with the model's lowercase choices.
    if instance.is_superuser:
        profile.role = 'admin'
    elif profile.role == 'Admin':
        profile.role = 'pharmacist'

    profile.save()

def _skip_flag(instance):
    """Check if an instance has the stock-update skip flag set (used by views
    that handle stock updates themselves to avoid double-counting)."""
    return getattr(instance, '_skip_stock_signal', False)


@receiver(pre_save, sender=Medicine)
def _medicine_store_old_stock(sender, instance, **kwargs):
    if instance.pk:
        instance._old_current_stock = Medicine.objects.filter(pk=instance.pk).values_list(
            'current_stock', flat=True
        ).first() or 0
    else:
        instance._old_current_stock = 0


@receiver(post_save, sender=Medicine)
def _medicine_record_stock_adjustment(sender, instance, created, **kwargs):
    delta = instance.current_stock - getattr(instance, '_old_current_stock', 0)
    if delta:
        record_stock_movement(
            instance,
            'adjustment',
            delta,
            reference='Manual medicine stock adjustment',
        )


# ─── Batch → Medicine.current_stock sync (for manual batch changes) ───────

@receiver(pre_save, sender=Batch)
def _batch_store_old_remaining(sender, instance, **kwargs):
    """Store the previous quantity_remaining so post_save can compute delta."""
    if instance.pk:
        try:
            old = Batch.objects.values_list('quantity_remaining', flat=True).get(pk=instance.pk)
            instance._old_remaining = old
        except Batch.DoesNotExist:
            instance._old_remaining = 0
    else:
        instance._old_remaining = 0


@receiver(post_save, sender=Batch)
@transaction.atomic
def _batch_sync_medicine_stock(sender, instance, created, **kwargs):
    if _skip_flag(instance):
        return
    old = getattr(instance, '_old_remaining', 0)
    delta = instance.quantity_remaining - old
    if delta != 0 and instance.medicine_id:
        Medicine.objects.filter(pk=instance.medicine_id).update(
            current_stock=models.F('current_stock') + delta
        )
        record_stock_movement(
            instance.medicine,
            'adjustment',
            delta,
            batch=instance,
            reference=f'Manual batch update #{instance.pk}',
        )


@receiver(post_delete, sender=Batch)
@transaction.atomic
def _batch_delete_restore_medicine_stock(sender, instance, **kwargs):
    if _skip_flag(instance):
        return
    if instance.quantity_remaining and instance.medicine_id:
        Medicine.objects.filter(pk=instance.medicine_id).update(
            current_stock=models.F('current_stock') - instance.quantity_remaining
        )
        record_stock_movement(
            instance.medicine,
            'adjustment',
            -instance.quantity_remaining,
            batch_number=instance.batch_number,
            reference=f'Batch #{instance.pk} deleted',
        )


# ─── DispensingItem → Batch & Medicine sync ──────────────────────────────

@receiver(pre_save, sender=DispensingItem)
def _dispensing_store_old_qty(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = DispensingItem.objects.select_related('batch', 'medicine').get(pk=instance.pk)
            instance._old_qty = old.quantity_dispensed
            instance._old_batch_id = old.batch_id
            instance._old_medicine_id = old.medicine_id
        except DispensingItem.DoesNotExist:
            instance._old_qty = 0
            instance._old_batch_id = None
            instance._old_medicine_id = None
    else:
        instance._old_qty = 0
        instance._old_batch_id = None
        instance._old_medicine_id = None


@receiver(post_save, sender=DispensingItem)
@transaction.atomic
def _dispensing_sync_stock(sender, instance, created, **kwargs):
    if _skip_flag(instance):
        return

    old_qty = getattr(instance, '_old_qty', 0)
    old_batch_id = getattr(instance, '_old_batch_id', None)
    old_medicine_id = getattr(instance, '_old_medicine_id', None)
    new_qty = instance.quantity_dispensed
    new_batch_id = instance.batch_id
    new_medicine_id = instance.medicine_id

    # Revert previous entry (if updating)
    if old_qty and old_batch_id and old_medicine_id:
        Batch.objects.filter(pk=old_batch_id).update(
            quantity_remaining=models.F('quantity_remaining') + old_qty
        )
        Medicine.objects.filter(pk=old_medicine_id).update(
            current_stock=models.F('current_stock') + old_qty
        )
        old_batch = Batch.objects.filter(pk=old_batch_id).first()
        record_stock_movement(
            Medicine.objects.get(pk=old_medicine_id),
            'correction',
            old_qty,
            movement_date=instance.prescription.dispensing_date,
            batch=old_batch,
            reference=f'Prescription {instance.prescription.prescription_ref} edit reversal',
        )

    # Apply new entry
    if new_qty and new_batch_id and new_medicine_id:
        Batch.objects.filter(pk=new_batch_id).update(
            quantity_remaining=models.F('quantity_remaining') - new_qty
        )
        Medicine.objects.filter(pk=new_medicine_id).update(
            current_stock=models.F('current_stock') - new_qty
        )
        record_stock_movement(
            Medicine.objects.get(pk=new_medicine_id),
            'dispense',
            -new_qty,
            movement_date=instance.prescription.dispensing_date,
            batch=Batch.objects.filter(pk=new_batch_id).first(),
            reference=f'Prescription {instance.prescription.prescription_ref}',
        )


@receiver(post_delete, sender=DispensingItem)
@transaction.atomic
def _dispensing_delete_restore_stock(sender, instance, **kwargs):
    if _skip_flag(instance):
        return
    qty = instance.quantity_dispensed
    if qty:
        if instance.batch_id:
            Batch.objects.filter(pk=instance.batch_id).update(
                quantity_remaining=models.F('quantity_remaining') + qty
            )
        if instance.medicine_id:
            Medicine.objects.filter(pk=instance.medicine_id).update(
                current_stock=models.F('current_stock') + qty
            )
            record_stock_movement(
                instance.medicine,
                'correction',
                qty,
                movement_date=getattr(instance, '_stock_prescription_date', None) or instance.prescription.dispensing_date,
                batch=instance.batch,
                reference=f'Prescription {getattr(instance, "_stock_prescription_ref", instance.prescription.prescription_ref)} deleted',
            )


@receiver(pre_delete, sender=DispensingItem)
def _dispensing_store_prescription_snapshot(sender, instance, **kwargs):
    prescription = Prescription.objects.filter(pk=instance.prescription_id).first()
    if prescription:
        instance._stock_prescription_date = prescription.dispensing_date
        instance._stock_prescription_ref = prescription.prescription_ref


# ─── OrderItem → Batch & Medicine sync (programmatic creation only) ───────

@receiver(post_save, sender=OrderItem)
@transaction.atomic
def _orderitem_create_batch_and_stock(sender, instance, created, **kwargs):
    """Handle OrderItem creation/update done outside of views (shell/admin).

    If quantity_received > 0 and the batch does not already exist, create it
    and increment Medicine.current_stock. The main order views use
    _create_batch_and_update_stock() directly, and flag instances with
    _skip_stock_signal to avoid duplication.
    """
    if _skip_flag(instance):
        return
    if not instance.quantity_received or instance.quantity_received <= 0:
        return

    from .models import OrderHeader
    if not instance.order_id or not OrderHeader.objects.filter(
        pk=instance.order_id, status='Delivered'
    ).exists():
        return

    from django.utils import timezone

    batch_number = instance.batch_number or 'N/A'
    medicine = instance.medicine
    if not medicine:
        return

    existing = Batch.objects.filter(
        batch_number=batch_number,
        medicine=medicine,
    ).first()

    # Derive effective receive date: receive_date -> order_date -> today
    received_on = None
    if instance.order_id:
        try:
            order_recv, order_dt = OrderHeader.objects.values_list(
                'receive_date', 'order_date'
            ).get(pk=instance.order_id)
            received_on = order_recv or order_dt
        except OrderHeader.DoesNotExist:
            received_on = None
    if received_on is None:
        received_on = timezone.now().date()

    expiry = instance.expiry_date or (
        timezone.now().date() + timezone.timedelta(days=365)
    )

    if existing:
        delta = instance.quantity_received
        updates = dict(
            quantity_received=models.F('quantity_received') + delta,
            quantity_remaining=models.F('quantity_remaining') + delta,
        )
        if not existing.date_received:
            updates['date_received'] = received_on
        Batch.objects.filter(pk=existing.pk).update(**updates)
        batch = existing
    else:
        batch = Batch(
            medicine=medicine,
            batch_number=batch_number,
            expiry_date=expiry,
            quantity_received=instance.quantity_received,
            quantity_remaining=instance.quantity_received,
            date_received=received_on,
            created_by=instance.created_by,
            updated_by=instance.updated_by,
        )
        batch._skip_stock_signal = True
        batch.save()

    Medicine.objects.filter(pk=medicine.pk).update(
        current_stock=models.F('current_stock') + instance.quantity_received
    )
    order = instance.order
    record_stock_movement(
        medicine,
        'receipt',
        instance.quantity_received,
        movement_date=received_on,
        batch=batch,
        reference=f'Purchase order {order.po_number}',
        po_number=order.po_number,
    )


@receiver(post_delete, sender=OrderItem)
@transaction.atomic
def _orderitem_delete_reverse_stock(sender, instance, **kwargs):
    if _skip_flag(instance):
        return
    if not instance.quantity_received or instance.quantity_received <= 0:
        return
    if not instance.medicine_id:
        return

    from .models import OrderHeader
    order = OrderHeader.objects.filter(pk=instance.order_id).first()
    order_status = getattr(instance, '_stock_order_status', None) or (
        order.status if order else None
    )
    if order_status != 'Delivered':
        return
    po_number = getattr(instance, '_stock_order_po_number', '') or (
        order.po_number if order else ''
    )
    received_on = getattr(instance, '_stock_order_receive_date', None) or (
        order.effective_receive_date if order else None
    )
    batch = Batch.objects.filter(
        medicine_id=instance.medicine_id,
        batch_number=instance.batch_number or 'N/A',
    ).first()
    record_stock_movement(
        instance.medicine,
        'correction',
        -instance.quantity_received,
        movement_date=received_on,
        batch=batch,
        reference=f'Purchase order {po_number} line deleted',
        po_number=po_number,
    )

    Medicine.objects.filter(pk=instance.medicine_id).update(
        current_stock=models.F('current_stock') - instance.quantity_received
    )
    # If a matching batch was created, try to remove the received qty from it.
    existing = Batch.objects.filter(
        medicine_id=instance.medicine_id,
        batch_number=instance.batch_number or 'N/A',
    ).first()
    if existing:
        new_remaining = existing.quantity_remaining - instance.quantity_received
        new_received = existing.quantity_received - instance.quantity_received
        if new_remaining <= 0 and new_received <= 0:
            existing._skip_stock_signal = True
            existing.delete()
        else:
            Batch.objects.filter(pk=existing.pk).update(
                quantity_remaining=max(0, new_remaining),
                quantity_received=max(0, new_received),
            )
    Medicine.objects.get(pk=instance.medicine_id).recompute_current_stock()


@receiver(pre_delete, sender=OrderItem)
def _orderitem_store_order_snapshot(sender, instance, **kwargs):
    from .models import OrderHeader
    order = OrderHeader.objects.filter(pk=instance.order_id).first()
    if order:
        instance._stock_order_po_number = order.po_number
        instance._stock_order_receive_date = order.effective_receive_date
        instance._stock_order_status = order.status
