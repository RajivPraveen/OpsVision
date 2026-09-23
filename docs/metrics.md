# Measures

Every rate on the dashboard uses one kind of record, so a filter does not invent a number that was never stored.

Service rates use the order line: one product on one order. Inventory is a daily snapshot of a product in a warehouse. Production numbers are one production run. Supplier lead time is a completed purchase order.

A plant or supplier filter changes orders, production, and purchasing. It does not assign a plant or supplier to a warehouse snapshot, because that snapshot does not have one.

| Measure | How it is calculated |
| --- | --- |
| On time and in full (OTIF) | Order lines delivered by the promise date and in full, divided by all order lines |
| Fill rate | Units delivered, divided by units ordered |
| Perfect order rate | On-time, in-full lines with no return, divided by all order lines |
| Backorder rate | Lines delivered short, divided by all order lines |
| Stockout rate | Daily product and warehouse snapshots below that day's demand, divided by all snapshots |
| Inventory turnover | Cost of goods on delivered units, divided by the average daily inventory value in the period |
| Days inventory outstanding | Days in the selected period, divided by turnover for that period |
| Supplier lead time | Average days from purchase-order placement to receipt |
| Forecast accuracy | `1 − (total absolute miss ÷ total actual demand)`, and never below zero |
| Defect rate | Defective units, divided by good units produced |
| Manufacturing yield | Good units, divided by planned units |
| Scrap rate | Scrap units, divided by planned units |
| Production downtime | Downtime minutes, divided by planned production minutes |
| Order cycle time | Average days from order placement to delivery |
| Cost per unit | Production cost, divided by good units |

## Why delivery moved

Each late or short order line stores one reason: supplier delay, production downtime, an inventory shortage, a transportation delay, or other. The chart converts each reason into its share of all order lines, then subtracts that share in the prior period from the current period.

Those shares add up to the change in on-time, in-full delivery before the numbers are rounded for display. In the default 28-day sample that is about **−3.14** points from supplier delays, **−2.57** from production downtime, **−1.43** from inventory shortages, and **−0.86** from transportation delays.

The same method is used when you split the change by supplier, plant, region, product, or material. It describes the reasons recorded on the orders. It is not a controlled experiment.

## Alerts

An alert compares the latest 14 days with the 90 days before them. It is raised only when both windows have enough history — at least 12 baseline observations and 3 recent ones — and the recent reading is more than 2.5 baseline standard deviations from the baseline average.

Supplier lead time, defect rate, and downtime use the recent average. Shipping delays and inventory movements use the most extreme recent day.

## The two-week estimate

Demand for the next 14 days is estimated separately for each product and warehouse. The estimate follows the recent pattern by weekday and adds a four-week trend, with that trend capped so one unusual month cannot run away with the number. The bias shown on each card is how far recent forecasts sat above or below actual orders.
