import * as React from "react";
import { ChartView } from "true-north-ui";

// Real shapes from tn governed queries (small/seed-42 dataset).

export const RevenueByRegionBar = () => (
  <ChartView
    chart={{
      type: "bar",
      title: "Net revenue by region",
      x_label: "region",
      y_label: "net revenue",
      y_format: "vnd",
      points: [
        { x: "South", y: 2612000000000 },
        { x: "North", y: 2144000000000 },
        { x: "Central", y: 1129000000000 },
      ],
      as_of: "2025-12-31",
    }}
  />
);

export const MarginByCategoryHBar = () => (
  <ChartView
    chart={{
      type: "hbar",
      title: "Gross margin by product category",
      x_label: "category",
      y_label: "gross margin",
      y_format: "vnd",
      points: [
        { x: "Accessory", y: 42700000000 },
        { x: "Gaming Gear", y: 7200000000 },
        { x: "Office Equipment", y: 3300000000 },
        { x: "Home Appliance", y: 2600000000 },
        { x: "Networking", y: 2200000000 },
        { x: "Monitor", y: -2400000000 },
        { x: "Desktop PC", y: -8200000000 },
        { x: "Phone & Tablet", y: -24100000000 },
        { x: "PC Component", y: -55600000000 },
        { x: "Laptop", y: -236300000000 },
      ],
      as_of: "2025-12-31",
    }}
  />
);

export const MonthlyTrendLine = () => (
  <ChartView
    chart={{
      type: "line",
      title: "Monthly net revenue trend, 2025",
      x_label: "month",
      y_label: "net revenue",
      y_format: "vnd",
      points: [
        { x: "2025-01-01", y: 401000000000 },
        { x: "2025-02-01", y: 356000000000 },
        { x: "2025-03-01", y: 442000000000 },
        { x: "2025-04-01", y: 471000000000 },
        { x: "2025-05-01", y: 512000000000 },
        { x: "2025-06-01", y: 489000000000 },
        { x: "2025-07-01", y: 530000000000 },
        { x: "2025-08-01", y: 547000000000 },
        { x: "2025-09-01", y: 498000000000 },
        { x: "2025-10-01", y: 541000000000 },
        { x: "2025-11-01", y: 583000000000 },
        { x: "2025-12-01", y: 515000000000 },
      ],
      as_of: "2025-12-31",
    }}
  />
);

export const KpiCard = () => (
  <ChartView
    chart={{
      type: "kpi",
      title: "Total net revenue",
      x_label: "",
      y_label: "net revenue",
      y_format: "vnd",
      points: [{ x: "Total net revenue", y: 5885154862000 }],
      as_of: "2025-12-31",
    }}
  />
);

export const RetentionByChannelBar = () => (
  <ChartView
    chart={{
      type: "bar",
      title: "Repeat-purchase rate (90d) by channel",
      x_label: "channel",
      y_label: "repeat-purchase rate",
      y_format: "percent",
      points: [
        { x: "b2b", y: 1.0 },
        { x: "app", y: 0.279 },
        { x: "web", y: 0.264 },
        { x: "in_store", y: 0.251 },
      ],
      as_of: "2025-12-31",
    }}
  />
);
