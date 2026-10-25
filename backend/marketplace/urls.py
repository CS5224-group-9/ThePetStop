from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("merchants/", views.MerchantListView.as_view(), name="merchant-list"),
    path(
        "merchants/<slug:slug>/",
        views.MerchantDetailView.as_view(),
        name="merchant-detail",
    ),
    path(
        "merchants/<slug:slug>/products/",
        views.MerchantProductListView.as_view(),
        name="merchant-products",
    ),
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path(
        "products/<int:pk>/", views.ProductDetailView.as_view(), name="product-detail"
    ),
]
