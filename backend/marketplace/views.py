from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Category, Merchant, Product
from .permissions import IsMerchant
from .serializers import (
    CategorySerializer,
    MerchantProductUpdateSerializer,
    MerchantProductWriteSerializer,
    MerchantSerializer,
    ProductDetailSerializer,
    ProductSerializer,
)


class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()


class MerchantListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = MerchantSerializer
    queryset = Merchant.objects.filter(active=True).order_by("name")


class MerchantDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = MerchantSerializer
    queryset = Merchant.objects.filter(active=True)
    lookup_field = "slug"


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = Product.objects.filter(
            active=True, merchant__active=True
        ).select_related("category", "merchant", "group")
        params = self.request.query_params
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(category__name__icontains=query)
                | Q(merchant__name__icontains=query)
            )
        for key, field in (("category", "category"), ("merchant", "merchant")):
            value = params.get(key)
            if not value:
                continue
            lookup = f"{field}_id" if value.isdigit() else f"{field}__slug"
            queryset = queryset.filter(**{lookup: value})
        for key, lookup in (("min_price", "gte"), ("max_price", "lte")):
            value = params.get(key)
            if value:
                try:
                    cents = int(value)
                except ValueError:
                    continue
                if cents >= 0:
                    queryset = queryset.filter(**{f"price_cents__{lookup}": cents})
        product_type = params.get("type")
        if product_type in {Product.PRODUCT, Product.SERVICE}:
            queryset = queryset.filter(product_type=product_type)
        species = params.get("species")
        if species:
            queryset = queryset.filter(
                Q(species__iexact=species) | Q(species__iexact="all pets")
            )
        sort = params.get("sort")
        if sort == "price_asc":
            queryset = queryset.order_by("price_cents", "name")
        elif sort == "price_desc":
            queryset = queryset.order_by("-price_cents", "name")
        elif sort == "name":
            queryset = queryset.order_by("name")
        return queryset


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductDetailSerializer
    queryset = Product.objects.filter(
        active=True, merchant__active=True
    ).select_related("category", "merchant", "group")


class MerchantProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        merchant = get_object_or_404(Merchant, slug=self.kwargs["slug"], active=True)
        return Product.objects.filter(merchant=merchant, active=True).select_related(
            "category", "merchant", "group"
        )


def owned_products(user):
    return Product.objects.filter(
        merchant__owner=user, merchant__active=True, active=True
    ).select_related("category", "merchant", "group")


def owned_merchant(user):
    return Merchant.objects.filter(owner=user, active=True).order_by("id").first()


class OwnedMerchantProductListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsMerchant]

    def get_queryset(self):
        return owned_products(self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MerchantProductWriteSerializer
        return ProductSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.method == "POST":
            context["merchant"] = owned_merchant(self.request.user)
        return context

    def create(self, request, *args, **kwargs):
        writer = self.get_serializer(data=request.data)
        writer.is_valid(raise_exception=True)
        product = writer.save()
        return Response(
            ProductSerializer(product, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class OwnedMerchantProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsMerchant]
    http_method_names = ["patch", "delete", "head", "options"]
    serializer_class = MerchantProductUpdateSerializer

    def get_queryset(self):
        return owned_products(self.request.user)

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=["active"])
