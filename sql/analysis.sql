-- SQLite: 基础行为总量及占比，按清洗后事件计。
SELECT behavior_type, COUNT(*) AS events,
       1.0 * COUNT(*) / (SELECT COUNT(*) FROM events) AS event_share
FROM events GROUP BY behavior_type ORDER BY behavior_type;

-- DAU 与购买用户数，不将事件占比误作用户转化率。
SELECT substr(event_time, 1, 10) AS day,
       COUNT(DISTINCT user_id) AS dau,
       COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) AS buyers
FROM events GROUP BY day ORDER BY day;

-- 周一开始自然周；首尾周可能不完整。
SELECT date(event_time, '-' || ((CAST(strftime('%w', event_time) AS INTEGER)
       + 6) % 7) || ' days') AS week_start,
       COUNT(DISTINCT user_id) AS wau
FROM events GROUP BY week_start ORDER BY week_start;

-- 热门类目，按独立买家排序。
SELECT category_id, COUNT(*) AS events,
       COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) AS buyers
FROM events JOIN items USING(item_id)
GROUP BY category_id ORDER BY buyers DESC LIMIT 20;

-- 热门商品。
SELECT item_id, COUNT(*) AS events, COUNT(DISTINCT user_id) AS users
FROM events GROUP BY item_id ORDER BY users DESC LIMIT 20;

-- 同一用户同一商品在不同小时发生多次购买；非订单口径。
WITH purchased_pairs AS (
    SELECT user_id, item_id, COUNT(*) AS purchase_hours
    FROM events WHERE behavior_type = 4 GROUP BY user_id, item_id
)
SELECT COUNT(*) AS purchased_pairs,
       SUM(CASE WHEN purchase_hours > 1 THEN 1 ELSE 0 END) AS repeated_pairs,
       AVG(CASE WHEN purchase_hours > 1 THEN 1.0 ELSE 0.0 END) AS repeat_pair_rate
FROM purchased_pairs;

-- 两步严格时序漏斗，同小时不算已知先后。
WITH pairs AS (
    SELECT user_id,item_id,
           MIN(CASE WHEN behavior_type=1 THEN event_time END) AS first_pv,
           MAX(CASE WHEN behavior_type=4 THEN event_time END) AS last_buy
    FROM events GROUP BY user_id,item_id
)
SELECT SUM(first_pv IS NOT NULL) AS viewed_pairs,
       SUM(CASE WHEN last_buy>first_pv THEN 1 ELSE 0 END) AS later_buy_pairs
FROM pairs;

-- 用户强度分组仅用于描述，不伪称完整 RFM。
WITH activity AS (SELECT user_id, COUNT(*) AS events FROM events GROUP BY user_id)
SELECT CASE WHEN events >= 100 THEN '100+' ELSE '<100' END AS activity_group,
       COUNT(*) AS users FROM activity GROUP BY activity_group;

-- 时间桶序列；同小时事件为并列，不人为规定行为顺序。
SELECT user_id, event_time, COUNT(*) AS events_in_hour,
       LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) AS prior_hour
FROM events GROUP BY user_id,event_time;
