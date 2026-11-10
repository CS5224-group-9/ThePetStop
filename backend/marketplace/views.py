import re

from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import checkout
from .models import CartItem, Category, Merchant, MerchantOrder, Order, Product
from .permissions import IsMerchant
from .serializers import (
    MAX_CART_QUANTITY,
    CartAddSerializer,
    CartQuantitySerializer,
    CategorySerializer,
    MerchantOrderStatusSerializer,
    MerchantProductUpdateSerializer,
    MerchantProductWriteSerializer,
    MerchantSerializer,
    OrderSerializer,
    OwnedMerchantOrderSerializer,
    ProductDetailSerializer,
    ProductSerializer,
    ShippingSerializer,
    cart_payload,
)

IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


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
        products = owned_products(self.request.user)
        if self.request.method == "PATCH":
            # Same row lock as checkout, so a price edit cannot save stale stock
            products = products.select_for_update(of=("self",))
        return products

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=["active"])


# Cart, checkout and orders: private to the signed-in user (the default permission)


class NoStoreMixin:
    """Private data: every response, errors included, is `no-store`."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


def stock_error(product: Product, quantity: int) -> ValidationError | None:
    if quantity <= product.stock:
        return None
    message = (
        "This item is out of stock."
        if product.stock == 0
        else f"Only {product.stock} left in stock."
    )
    return ValidationError({"quantity": [message]})


class CartView(NoStoreMixin, APIView):
    def get(self, request):
        return Response(cart_payload(request.user, {"request": request}))

    def delete(self, request):
        with checkout.locked_cart(request.user):
            CartItem.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemListView(NoStoreMixin, APIView):
    def post(self, request):
        """Add a product; adding one already in the cart increases its quantity."""
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]
        with checkout.locked_cart(request.user):
            line = CartItem.objects.filter(user=request.user, product=product).first()
            total = quantity + (line.quantity if line else 0)
            if total > MAX_CART_QUANTITY:
                raise ValidationError(
                    {
                        "quantity": [
                            f"You can add at most {MAX_CART_QUANTITY} of one item."
                        ]
                    }
                )
            if error := stock_error(product, total):
                raise error
            if line:
                line.quantity = total
                line.save(update_fields=["quantity"])
            else:
                CartItem.objects.create(
                    user=request.user, product=product, quantity=total
                )
        return Response(
            cart_payload(request.user, {"request": request}),
            status=status.HTTP_201_CREATED,
        )


class CartItemDetailView(NoStoreMixin, APIView):
    def get_line(self, request, product_id):
        return get_object_or_404(
            CartItem.objects.select_related("product__merchant"),
            user=request.user,
            product_id=product_id,
        )

    def patch(self, request, product_id):
        """Set the quantity of a product already in the cart."""
        serializer = CartQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]
        with checkout.locked_cart(request.user):
            line = self.get_line(request, product_id)
            product = line.product
            if not (product.active and product.merchant.active):
                raise ValidationError(
                    {
                        "product": [
                            "This item is no longer available. Remove it instead."
                        ]
                    }
                )
            if error := stock_error(product, quantity):
                raise error
            line.quantity = quantity
            line.save(update_fields=["quantity"])
        return Response(cart_payload(request.user, {"request": request}))

    def delete(self, request, product_id):
        with checkout.locked_cart(request.user):
            self.get_line(request, product_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CheckoutView(NoStoreMixin, APIView):
    def post(self, request):
        """Place a paid (simulated) order from the whole cart."""
        key = request.headers.get("Idempotency-Key", "").strip()
        if not IDEMPOTENCY_KEY.match(key):
            raise ValidationError(
                {
                    "idempotency_key": [
                        "Send an Idempotency-Key header of 8 to 80 letters, "
                        "digits, hyphens or underscores."
                    ]
                }
            )
        serializer = ShippingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, created = checkout.place_order(
            request.user, serializer.validated_data, key
        )
        order = order_queryset(request.user).get(pk=order.pk)
        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def order_queryset(user):
    return (
        Order.objects.filter(user=user)
        .prefetch_related(
            Prefetch(
                "merchant_orders",
                queryset=MerchantOrder.objects.select_related(
                    "merchant"
                ).prefetch_related("items"),
            )
        )
        .order_by("-created_at", "-pk")
    )


class OrderListView(NoStoreMixin, generics.ListAPIView):
    serializer_class = OrderSerializer

    def get_queryset(self):
        return order_queryset(self.request.user)


class OrderDetailView(NoStoreMixin, generics.RetrieveAPIView):
    serializer_class = OrderSerializer

    def get_queryset(self):
        # Another user's order is a 404, never a 403
        return order_queryset(self.request.user)


def owned_merchant_orders(user):
    return (
        MerchantOrder.objects.filter(merchant__owner=user, merchant__active=True)
        .select_related("merchant", "order")
        .prefetch_related("items")
        .order_by("-order__created_at", "-pk")
    )


class OwnedMerchantOrderListView(NoStoreMixin, generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsMerchant]
    serializer_class = OwnedMerchantOrderSerializer

    def get_queryset(self):
        return owned_merchant_orders(self.request.user)


class OwnedMerchantOrderDetailView(NoStoreMixin, APIView):
    permission_classes = [IsAuthenticated, IsMerchant]

    def patch(self, request, pk):
        serializer = MerchantOrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            row = get_object_or_404(
                owned_merchant_orders(request.user).select_for_update(of=("self",)),
                pk=pk,
            )
            transitions = {
                MerchantOrder.PAID: MerchantOrder.PROCESSING,
                MerchantOrder.PROCESSING: MerchantOrder.SHIPPED,
                MerchantOrder.SHIPPED: MerchantOrder.DELIVERED,
            }
            next_status = serializer.validated_data["status"]
            if transitions.get(row.status) != next_status:
                raise ValidationError(
                    {"status": ["Move to the next fulfilment status in sequence."]}
                )
            row.status = next_status
            row.save(update_fields=["status", "updated_at"])
        return Response(OwnedMerchantOrderSerializer(row).data)
