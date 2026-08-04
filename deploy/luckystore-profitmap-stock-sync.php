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
    $stock_by_product_id = [];

    foreach ($items as $item) {
        $sku = isset($item['sku']) ? wc_clean((string) $item['sku']) : '';
        if ($sku === '') {
            $invalid[] = $item;
            continue;
        }

        $stock = max(0, (int) ($item['stock'] ?? 0));
        $product_id = wc_get_product_id_by_sku($sku);
        $matched_sku = $sku;
        if (!$product_id) {
            $base_sku = profitmap_stock_sync_base_sku($sku);
            if ($base_sku !== $sku) {
                $product_id = wc_get_product_id_by_sku($base_sku);
                $matched_sku = $base_sku;
            }
            if (!$product_id) {
                $missing[] = $sku;
                continue;
            }
        }

        if (!isset($stock_by_product_id[$product_id])) {
            $stock_by_product_id[$product_id] = [
                'stock' => 0,
                'matched_sku' => $matched_sku,
                'source_skus' => [],
            ];
        }
        $stock_by_product_id[$product_id]['stock'] += $stock;
        $stock_by_product_id[$product_id]['source_skus'][] = $sku;
    }

    foreach ($stock_by_product_id as $product_id => $row) {
        $product = wc_get_product($product_id);
        if (!$product) {
            $missing = array_merge($missing, $row['source_skus']);
            continue;
        }

        $stock = max(0, (int) $row['stock']);
        $product->set_manage_stock(true);
        $product->set_stock_quantity($stock);
        $product->set_stock_status($stock > 0 ? 'instock' : 'outofstock');
        $product->save();
        wc_delete_product_transients($product_id);

        $updated[] = [
            'sku' => $row['matched_sku'],
            'product_id' => $product_id,
            'stock' => $stock,
            'source_skus' => $row['source_skus'],
        ];
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
