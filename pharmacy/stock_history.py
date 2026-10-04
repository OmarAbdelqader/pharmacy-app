from uuid import uuid4

from django.utils import timezone

from .models import StockMovement


def record_stock_movement(
    medicine,
    movement_type,
    quantity_delta,
    movement_date=None,
    batch=None,
    batch_number='',
    reference='',
    po_number='',
    source_key=None,
    is_reconstructed=False,
    quantity_unit='',
    affects_stock_balance=True,
):
    if not quantity_delta:
        return None

    return StockMovement.objects.create(
        medicine=medicine,
        batch=batch,
        batch_number=batch_number or (batch.batch_number if batch else ''),
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        quantity_unit=quantity_unit or medicine.unit,
        affects_stock_balance=affects_stock_balance,
        movement_date=movement_date or timezone.now().date(),
        reference=reference,
        po_number=po_number,
        source_key=source_key or f'event:{uuid4().hex}',
        is_reconstructed=is_reconstructed,
    )