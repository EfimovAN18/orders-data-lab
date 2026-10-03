-- Агрегация позиций: не суммируем total_kopecks заказа после JOIN с позициями.
SELECT p.category,
       SUM(i.quantity) AS units_sold,
       SUM(i.line_total_kopecks) AS revenue_kopecks,
       COUNT(DISTINCT o.order_id) AS paid_orders
FROM fact_order_items AS i
JOIN fact_orders AS o ON o.order_id = i.order_id
JOIN dim_products AS p ON p.product_id = i.product_id
WHERE o.status = 'paid'
GROUP BY p.category
ORDER BY revenue_kopecks DESC, p.category;
