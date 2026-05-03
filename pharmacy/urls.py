from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Medicines
    path('medicines/', views.medicine_list, name='medicine_list'),
    path('medicines/add/', views.medicine_add, name='medicine_add'),
    path('medicines/<int:pk>/edit/', views.medicine_edit, name='medicine_edit'),
    path('medicines/<int:pk>/delete/', views.medicine_delete, name='medicine_delete'),
    path('api/medicine/<int:pk>/', views.medicine_api, name='medicine_api'),
    path('api/medicine/search/', views.medicine_search_api, name='medicine_search_api'),
    path('api/medicine/<int:pk>/batches/', views.medicine_batches_api, name='medicine_batches_api'),

    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.supplier_add, name='supplier_add'),
    path('suppliers/<int:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),

    # Codes
    path('codes/', views.code_list, name='code_list'),
    path('codes/add/', views.code_add, name='code_add'),
    path('codes/<int:pk>/delete/', views.code_delete, name='code_delete'),

    # Prescriptions
    path('prescriptions/', views.prescription_list, name='prescription_list'),
    path('prescriptions/add/', views.prescription_add, name='prescription_add'),
    path('prescriptions/<int:pk>/edit/', views.prescription_edit, name='prescription_edit'),
    path('prescriptions/<int:pk>/delete/', views.prescription_delete, name='prescription_delete'),

    # Orders
    path('orders/', views.order_list, name='order_list'),
    path('orders/add/', views.order_add, name='order_add'),
    path('orders/<int:pk>/edit/', views.order_edit, name='order_edit'),
    path('orders/<int:pk>/delete/', views.order_delete, name='order_delete'),

    # Reports
    path('reports/stock-movement/', views.report_stock_movement, name='report_stock_movement'),
    path('reports/current-stock/', views.report_current_stock, name='report_current_stock'),
    path('reports/expiry/', views.report_expiry, name='report_expiry'),
    path('reports/under-supply/', views.report_under_supply, name='report_under_supply'),
    path('reports/low-stock/', views.report_low_stock, name='report_low_stock'),
    path('reports/daily-dispensing/', views.report_daily_dispensing, name='report_daily_dispensing'),

    # Users
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.user_add, name='user_add'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/reset-password/', views.user_reset_password, name='user_reset_password'),
]