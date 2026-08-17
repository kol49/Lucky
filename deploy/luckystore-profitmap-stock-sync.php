<?php
/**
 * Plugin Name: LuckyStore ProfitMap Stock Sync
 * Description: Receives protected stock updates from ProfitMap and applies them to WooCommerce products by SKU.
 * Version: 0.1.0
 */

if (!defined('ABSPATH')) {
    exit;
}

add_action('rest_api_init', function () {
    register_rest_route('profitmap/v1', '/stock-sync', [
        'methods' => 'POST',
        'callback' => 'profitmap_stock_sync_update',
        'permission_callback' => 'profitmap_stock_sync_authorize',
    ]);
});

add_action('woocommerce_order_status_shipped', 'profitmap_stock_sync_send_order_sale', 20, 1);
add_action('woocommerce_order_status_completed', 'profitmap_stock_sync_send_order_sale', 20, 1);
add_action('woocommerce_order_status_cancelled', 'profitmap_stock_sync_send_order_sale', 20, 1);
add_action('woocommerce_order_status_refunded', 'profitmap_stock_sync_send_order_sale', 20, 1);
add_action('woocommerce_order_status_failed', 'profitmap_stock_sync_send_order_sale', 20, 1);
add_action('woocommerce_order_status_not-picked-up', 'profitmap_stock_sync_send_order_sale', 20, 1);

function profitmap_stock_sync_authorize(WP_REST_Request $request): bool
{
    $token = defined('PROFITMAP_STOCK_SYNC_TOKEN') ? (string) PROFITMAP_STOCK_SYNC_TOKEN : (string) getenv('PROFITMAP_STOCK_SYNC_TOKEN');
    if ($token === '') {
        return false;
    }

    $authorization = (string) $request->get_header('authorization');
    if (!preg_match('/^Bearer\s+(.+)$/i', $authorization, $matches)) {
        return false;
    }

    return hash_equals($token, trim($matches[1]));
}

function profitmap_stock_sync_update(WP_REST_Request $request)
{
    if (!function_exists('wc_get_product_id_by_sku') || !function_exists('wc_get_product')) {
        return new WP_Error('woocommerce_missing', 'WooCommerce is not available.', ['status' => 500]);
    }

    $items = $request->get_param('items');
    if (!is_array($items)) {
        return new WP_Error('invalid_payload', 'Expected an items array.', ['status' => 400]);
    }

    $updated = [];
    $missing = [];
    $invalid = [];
    $stock_by_sku = [];

    foreach ($items as $item) {
        $sku = isset($item['sku']) ? wc_clean((string) $item['sku']) : '';
        if ($sku === '') {
            $invalid[] = $item;
            continue;
        }

        $stock = max(0, (int) ($item['stock'] ?? 0));
        $matched_sku = $sku;
        $product_ids = profitmap_stock_sync_product_ids_by_sku($sku);
        if (!$product_ids) {
            $base_sku = profitmap_stock_sync_base_sku($sku);
            if ($base_sku !== $sku) {
                $product_ids = profitmap_stock_sync_product_ids_by_sku($base_sku);
                $matched_sku = $base_sku;
            }
            if (!$product_ids) {
                $missing[] = $sku;
                continue;
            }
        }

        if (!isset($stock_by_sku[$matched_sku])) {
            $stock_by_sku[$matched_sku] = [
                'stock' => 0,
                'matched_sku' => $matched_sku,
                'source_skus' => [],
            ];
        }
        $stock_by_sku[$matched_sku]['stock'] += $stock;
        $stock_by_sku[$matched_sku]['source_skus'][] = $sku;
    }

    foreach ($stock_by_sku as $row) {
        $product_ids = profitmap_stock_sync_product_ids_by_sku($row['matched_sku']);
        if (!$product_ids) {
            $missing = array_merge($missing, $row['source_skus']);
            continue;
        }

        $unit_stock = max(0, (int) $row['stock']);
        foreach ($product_ids as $product_id) {
            $product = wc_get_product($product_id);
            if (!$product) {
                $missing = array_merge($missing, $row['source_skus']);
                continue;
            }

            $pack_multiplier = profitmap_stock_sync_product_pack_multiplier($product);
            $stock = intdiv($unit_stock, $pack_multiplier);
            $product->set_manage_stock(true);
            $product->set_stock_quantity($stock);
            $product->set_stock_status($stock > 0 ? 'instock' : 'outofstock');
            $product->save();
            wc_delete_product_transients($product_id);

            $updated[] = [
                'sku' => $row['matched_sku'],
                'product_id' => $product_id,
                'stock' => $stock,
                'unit_stock' => $unit_stock,
                'pack_multiplier' => $pack_multiplier,
                'source_skus' => $row['source_skus'],
            ];
        }
    }

    return rest_ensure_response([
        'ok' => true,
        'updated' => $updated,
        'missing' => $missing,
        'invalid_count' => count($invalid),
    ]);
}

function profitmap_stock_sync_base_sku(string $sku): string
{
    $parts = preg_split('/[\s(#]/u', $sku, 2);
    $base_sku = is_array($parts) && isset($parts[0]) ? trim($parts[0]) : $sku;
    return $base_sku !== '' ? $base_sku : $sku;
}

function profitmap_stock_sync_product_ids_by_sku(string $sku): array
{
    global $wpdb;

    $sku = trim($sku);
    if ($sku === '') {
        return [];
    }

    $ids = $wpdb->get_col($wpdb->prepare(
        "SELECT DISTINCT posts.ID
         FROM {$wpdb->posts} posts
         INNER JOIN {$wpdb->postmeta} sku_meta ON sku_meta.post_id = posts.ID
         WHERE sku_meta.meta_key = '_sku'
           AND sku_meta.meta_value = %s
           AND posts.post_type IN ('product', 'product_variation')
           AND posts.post_status NOT IN ('trash', 'auto-draft')
         ORDER BY posts.post_type = 'product' DESC, posts.ID ASC",
        $sku
    ));

    $product_ids = array_values(array_map('intval', $ids ?: []));
    foreach ($product_ids as $product_id) {
        $product = wc_get_product($product_id);
        if ($product && $product->is_type('variable')) {
            $product_ids = array_merge($product_ids, array_map('intval', $product->get_children()));
        }
    }

    return array_values(array_unique($product_ids));
}

function profitmap_stock_sync_product_pack_multiplier($product): int
{
    if (!$product || !method_exists($product, 'get_parent_id') || !$product->get_parent_id()) {
        return 1;
    }

    foreach ((array) $product->get_attributes() as $value) {
        $multiplier = profitmap_stock_sync_parse_pack_multiplier((string) $value);
        if ($multiplier > 1) {
            return $multiplier;
        }
    }

    return 1;
}

function profitmap_stock_sync_order_item_pack_multiplier($item, $product): int
{
    $multiplier = profitmap_stock_sync_product_pack_multiplier($product);
    if ($multiplier > 1) {
        return $multiplier;
    }

    foreach ($item->get_meta_data() as $meta) {
        $data = $meta->get_data();
        foreach (['display_value', 'value'] as $key) {
            $value = isset($data[$key]) ? $data[$key] : '';
            if (is_array($value)) {
                $value = implode(' ', $value);
            }
            $multiplier = profitmap_stock_sync_parse_pack_multiplier((string) $value);
            if ($multiplier > 1) {
                return $multiplier;
            }
        }
    }

    return 1;
}

function profitmap_stock_sync_parse_pack_multiplier(string $text): int
{
    if (preg_match('/(?<!\d)([1-9]\d*)\s*шт\.?/iu', $text, $matches)) {
        return max(1, (int) $matches[1]);
    }

    return 1;
}

function profitmap_stock_sync_send_order_sale($order_id): void
{
    if (!function_exists('wc_get_order')) {
        return;
    }

    $url = defined('PROFITMAP_SALES_SYNC_URL') ? (string) PROFITMAP_SALES_SYNC_URL : (string) getenv('PROFITMAP_SALES_SYNC_URL');
    $token = defined('PROFITMAP_SALES_SYNC_TOKEN') ? (string) PROFITMAP_SALES_SYNC_TOKEN : (string) getenv('PROFITMAP_SALES_SYNC_TOKEN');
    if ($url === '' || $token === '') {
        return;
    }

    $order = wc_get_order($order_id);
    if (!$order) {
        return;
    }

    $items = [];
    foreach ($order->get_items('line_item') as $item_id => $item) {
        $product = $item->get_product();
        if (!$product) {
            continue;
        }
        $sku = $product->get_sku();
        if ($sku === '' && $product->get_parent_id()) {
            $parent = wc_get_product($product->get_parent_id());
            $sku = $parent ? $parent->get_sku() : '';
        }
        if ($sku === '') {
            continue;
        }

        $ordered_quantity = max(0, (int) $item->get_quantity());
        if (!$ordered_quantity) {
            continue;
        }

        $pack_multiplier = profitmap_stock_sync_order_item_pack_multiplier($item, $product);
        $quantity = $ordered_quantity * $pack_multiplier;
        $line_total = (float) $item->get_total();
        $items[] = [
            'sku' => $sku,
            'quantity' => $quantity,
            'unit_price' => round($line_total / $quantity, 4),
            'name' => $item->get_name(),
            'external_id' => $order->get_id() . ':' . $item_id,
        ];
    }

    $created = $order->get_date_created();
    $payload = [
        'order_id' => (string) $order->get_id(),
        'order_number' => (string) $order->get_order_number(),
        'status' => $order->get_status(),
        'sale_date' => $created ? $created->date('Y-m-d') : gmdate('Y-m-d'),
        'items' => $items,
    ];

    wp_remote_post($url, [
        'timeout' => 8,
        'sslverify' => false,
        'headers' => [
            'Authorization' => 'Bearer ' . $token,
            'Content-Type' => 'application/json',
            'Accept' => 'application/json',
        ],
        'body' => wp_json_encode($payload),
    ]);
}
