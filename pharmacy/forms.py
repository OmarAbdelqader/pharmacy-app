from django import forms
from django.contrib.auth.models import User
from django.forms.widgets import DateInput as _DateInput
from .models import Medicine, MedicineCode, Supplier, Batch, OrderHeader, OrderItem, Prescription, DispensingItem, UserProfile


class _MonthDateInput(_DateInput):
    """DateInput that formats datetime.date → YYYY-MM for the HTML month picker."""

    input_type = 'month'

    def format_value(self, value):
        if not value:
            return ''
        if hasattr(value, 'year'):
            return f'{value.year:04d}-{value.month:02d}'
        s = str(value)
        if len(s) >= 7 and s[4] == '-':
            return s[:7]
        return s


class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        fields = [
            'name', 'category', 'book_reference',
            'unit', 'reorder_level', 'default_dispense_qty', 'description'
        ]
        # Note: current_stock is excluded — updated automatically
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم الصنف'
            }),
            'category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'نوع الصنف'
            }),
            'book_reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 4-189'
            }),
            'unit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: حبة، علبة، زجاجة'
            }),
            'reorder_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0'
            }),
            'default_dispense_qty': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري'
            }),
        }
        labels = {
            'name': 'اسم الصنف',
            'category': 'نوع الصنف',
            'book_reference': 'دفتر 118',
            'unit': 'الوحدة',
            'reorder_level': 'حد إعادة الطلب',
            'default_dispense_qty': 'الكمية الافتراضية للصرف',
            'description': 'الوصف',
        }

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_person', 'phone', 'email', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم المورد'
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم الشخص المسؤول'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم الهاتف'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'البريد الإلكتروني'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'العنوان'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ملاحظات اختيارية'
            }),
        }
        labels = {
            'name': 'اسم المورد',
            'contact_person': 'الشخص المسؤول',
            'phone': 'رقم الهاتف',
            'email': 'البريد الإلكتروني',
            'address': 'العنوان',
            'notes': 'ملاحظات',
        }

class MedicineCodeForm(forms.ModelForm):
    class Meta:
        model = MedicineCode
        fields = ['medicine', 'code']
        widgets = {
            'medicine': forms.Select(attrs={
                'class': 'form-select',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'أدخل الكود'
            }),
        }
        labels = {
            'medicine': 'الصنف',
            'code': 'الكود',
        }

class OrderHeaderForm(forms.ModelForm):
    class Meta:
        model = OrderHeader
        fields = [
            'supplier', 'supplier_reference', 'order_date',
            'receive_date', 'status', 'received_by', 'notes'
        ]
        widgets = {
            'supplier': forms.Select(attrs={
                'class': 'form-select',
            }),
            'supplier_reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم مرجع المورد'
            }),
            'order_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'receive_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select',
            }),
            'received_by': forms.Select(attrs={
                'class': 'form-select',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ملاحظات اختيارية'
            }),
        }
        labels = {
            'supplier': 'المورد',
            'supplier_reference': 'رقم مرجع المورد',
            'order_date': 'تاريخ الطلب',
            'receive_date': 'تاريخ الاستلام الفعلي',
            'status': 'حالة الطلب',
            'received_by': 'الصيدلي المستلم',
            'notes': 'ملاحظات',
        }

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data


class OrderItemForm(forms.ModelForm):
    expiry_date = forms.DateField(
        required=False,
        widget=_MonthDateInput(attrs={
            'class': 'form-control',
        }),
        input_formats=['%Y-%m', '%Y-%m-%d']
    )

    class Meta:
        model = OrderItem
        fields = [
            'medicine', 'quantity_ordered', 'quantity_received',
            'unit_cost', 'batch_number', 'expiry_date'
        ]
        widgets = {
            'medicine': forms.Select(attrs={
                'class': 'form-select'
            }),
            'quantity_ordered': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'min': '0'
            }),
            'quantity_received': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'min': '0'
            }),
            'unit_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'batch_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم التشغيلة'
            }),
        }
        labels = {
            'medicine': 'الصنف',
            'quantity_ordered': 'الكمية المطلوبة',
            'quantity_received': 'الكمية المستلمة',
            'unit_cost': 'سعر الوحدة',
            'batch_number': 'رقم التشغيلة',
            'expiry_date': 'تاريخ الانتهاء',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quantity_ordered'].required = False
        self.fields['quantity_ordered'].empty_value = 0
        self.fields['quantity_received'].required = False
        self.fields['quantity_received'].empty_value = 0
        self.fields['unit_cost'].required = False
        self.fields['batch_number'].required = False

    def clean_quantity_ordered(self):
        v = self.cleaned_data.get('quantity_ordered')
        return 0 if v in (None, '') else v

    def clean_quantity_received(self):
        v = self.cleaned_data.get('quantity_received')
        return 0 if v in (None, '') else v

    def clean_unit_cost(self):
        v = self.cleaned_data.get('unit_cost')
        return None if v in (None, '') else v

    def clean_batch_number(self):
        v = self.cleaned_data.get('batch_number')
        return '' if v in (None,) else (v or '')

class PrescriptionForm(forms.ModelForm):
    prefix_digits = forms.CharField(
        max_length=3,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center fw-bold fs-5',
            'placeholder': '000',
            'maxlength': '3',
            'style': 'width: 80px;'
        }),
        label='البادئة'
    )
    suffix_digits = forms.CharField(
        max_length=3,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center fw-bold fs-5',
            'placeholder': '000',
            'maxlength': '3',
            'style': 'width: 80px;',
            'autofocus': True
        }),
        label='الرقم'
    )

    class Meta:
        model = Prescription
        fields = ['dispensing_date']
        widgets = {
            'dispensing_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }
        labels = {
            'dispensing_date': 'تاريخ الصرف',
        }

    def clean(self):
        cleaned_data = super().clean()
        prefix = cleaned_data.get('prefix_digits', '')
        suffix = cleaned_data.get('suffix_digits', '')
        if prefix and suffix:
            cleaned_data['prescription_ref'] = prefix + suffix
        return cleaned_data


class DispensingItemForm(forms.ModelForm):
    medicine_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'أدخل الكود',
        }),
        label='الكود'
    )

    class Meta:
        model = DispensingItem
        fields = ['medicine', 'batch', 'quantity_dispensed']
        widgets = {
            'medicine': forms.Select(attrs={
                'class': 'form-select'
            }),
            'batch': forms.Select(attrs={
                'class': 'form-select'
            }),
            'quantity_dispensed': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
        }
        labels = {
            'medicine': 'الصنف',
            'batch': 'التشغيلة',
            'quantity_dispensed': 'الكمية المصروفة',
        }


class UserForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'كلمة المرور',
        }),
        label='كلمة المرور'
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم المستخدم'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'الاسم الأول'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم العائلة'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'البريد الإلكتروني'
            }),
        }
        labels = {
            'username': 'اسم المستخدم',
            'first_name': 'الاسم الأول',
            'last_name': 'اسم العائلة',
            'email': 'البريد الإلكتروني',
            'password': 'كلمة المرور',
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['role']
        widgets = {
            'role': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
        labels = {
            'role': 'الدور',
        }


class PasswordResetForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'كلمة المرور الجديدة'
        }),
        label='كلمة المرور الجديدة'
    )