-- LAG сравнивает месяцы. Календарь сохраняет месяцы без заказов.
WITH RECURSIVE calendar(month) AS (
    SELECT DATE(MIN(order_date), 'start of month') FROM fact_orders
    HAVING MIN(order_date) IS NOT NULL
    UNION ALL
    SELECT DATE(month, '+1 month') FROM calendar
    WHERE month < (SELECT DATE(MAX(order_date), 'start of month') FROM fact_orders)
), monthly AS (
    SELECT c.month,
           COALESCE(SUM(CASE WHEN o.status = 'paid' THEN o.total_kopecks ELSE 0 END), 0)
               AS revenue_kopecks,
           COUNT(CASE WHEN o.status = 'paid' THEN o.order_id END) AS paid_orders
    FROM calendar AS c
    LEFT JOIN fact_orders AS o ON DATE(o.order_date, 'start of month') = c.month
    GROUP BY c.month
), previous AS (
    SELECT *, LAG(revenue_kopecks) OVER (ORDER BY month) AS previous_revenue
    FROM monthly
)
SELECT month, revenue_kopecks, paid_orders,
       ROUND(100.0 * (revenue_kopecks - previous_revenue) / NULLIF(previous_revenue, 0), 2)
           AS growth_percent
FROM previous ORDER BY month;
