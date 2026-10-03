-- Повторный покупатель: минимум два оплаченных заказа во всём снимке.
WITH buyers AS (
    SELECT customer_id, COUNT(*) AS paid_order_count
    FROM fact_orders WHERE status = 'paid' GROUP BY customer_id
)
SELECT
    COUNT(*) AS total_orders,
    COALESCE(SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END), 0) AS paid_orders,
    COALESCE(SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_orders,
    COALESCE(SUM(CASE WHEN status = 'paid' THEN total_kopecks ELSE 0 END), 0) AS revenue_kopecks,
    (SELECT COUNT(*) FROM buyers) AS paying_customers,
    (SELECT COUNT(*) FROM buyers WHERE paid_order_count >= 2) AS repeat_customers,
    MIN(order_date) AS date_from,
    MAX(order_date) AS date_to
FROM fact_orders;
