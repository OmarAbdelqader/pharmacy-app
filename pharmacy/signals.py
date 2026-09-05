from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import models
from django.contrib.auth.models import User
from .models import UserProfile, Batch, DispensingItem, OrderItem, Medicine


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


def _skip_flag(instance):
    """Check if an instance has the stock-update skip flag set (used by views
    that handle stock updates themselves to avoid double-counting)."""
    return getattr(instance, '_skip_stock_signal', False)


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
def _batch_sync_medicine_stock(sender, instance, created, **kwargs):
    if _skip_flag(instance):
        return
    old = getattr(instance, '_old_remaining', 0)
    delta = instance.quantity_remaining - old
    if delta != 0 and instance.medicine_id:
        Medicine.objects.filter(pk=instance.medicine_id).update(
            current_stock=models.F('current_stock') + delta
        )


@receiver(post_delete, sender=Batch)
def _batch_delete_restore_medicine_stock(sender, instance, **kwargs):
    if _skip_flag(instance):
        return
    if instance.quantity_remaining and instance.medicine_id:
        Medicine.objects.filter(pk=instance.medicine_id).update(
            current_stock=models.F('current_stock') - instance.quantity_remaining
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

    # Apply new entry
    if new_qty and new_batch_id and new_medicine_id:
        Batch.objects.filter(pk=new_batch_id).update(
            quantity_remaining=models.F('quantity_remaining') - new_qty
        )
        Medicine.objects.filter(pk=new_medicine_id).update(
            current_stock=models.F('current_stock') - new_qty
        )


@receiver(post_delete, sender=DispensingItem)
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


# ─── OrderItem → Batch & Medicine sync (programmatic creation only) ───────

@receiver(post_save, sender=OrderItem)
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
    else:
        Batch.objects.create(
            medicine=medicine,
            batch_number=batch_number,
            expiry_date=expiry,
            quantity_received=instance.quantity_received,
            quantity_remaining=instance.quantity_received,
            date_received=received_on,
            created_by=instance.created_by,
            updated_by=instance.updated_by,
        )

    Medicine.objects.filter(pk=medicine.pk).update(
        current_stock=models.F('current_stock') + instance.quantity_received
    )


@receiver(post_delete, sender=OrderItem)
def _orderitem_delete_reverse_stock(sender, instance, **kwargs):
    if _skip_flag(instance):
        return
    if not instance.quantity_received or instance.quantity_received <= 0:
        return
    if not instance.medicine_id:
        return

    Medicine.objects.filter(pk=instance.medicine_id).update(
        current_stock=models.F('current_stock') - instance.quantity_received
    )
    # If a matching batch was created, try to remove the received qty from it.
    if instance.batch_number:
        existing = Batch.objects.filter(
            medicine_id=instance.medicine_id,
            batch_number=instance.batch_number,
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
