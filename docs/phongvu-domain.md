# Phong Vũ — Domain Research

Background for the `true_north` demo dataset. Phong Vũ (phongvu.vn) is a Vietnamese
consumer-electronics retailer. Facts below are verified against the cited source URLs;
anything not verifiable is explicitly marked **ASSUMPTION**. The synthetic dataset is a
plausible *model* of this business, not real Phong Vũ data.

## Ownership

- **Owner: Teko Technology (Công ty CP Công nghệ Teko Việt Nam)**, which invested in /
  took over Phong Vũ in **2018**. Teko is part of the **VNLIFE** holding group (same group
  behind **VNPAY**). Chain: VNLIFE → Teko → Phong Vũ. The Phong Vũ mobile app's package id
  `vn.teko.android.consumer.phongvu` carries the Teko namespace, corroborating this.
  - Sources: https://help.phongvu.vn/ , https://play.google.com/store/apps/details?id=vn.teko.android.consumer.phongvu
- **Digiworld is NOT an owner.** Digiworld (DGW) is a wholesale distributor that sells
  *to* Phong Vũ (a receivables/customer relationship), alongside Thế Giới Di Động and FPT Shop.
- Exact 2018 deal structure / stake % — **ASSUMPTION (unverified)**; source (brandsvietnam) 403'd.

## Product categories & brands

Top-level categories (from phongvu.vn nav + store description):

- Laptops
- Apple products (MacBook / iPhone / iPad / accessories)
- Desktop PCs (PC – Máy tính bàn), incl. gaming PCs and DIY custom builds
- Computer monitors (màn hình)
- Computer components / linh kiện (CPU, GPU, RAM, SSD, mainboard, PSU — DIY build parts)
- Computer accessories (keyboards, mice, webcams, cables, docks)
- Gaming gear / peripherals (mechanical keyboards, gaming mice, headsets, chairs)
- Phones / tablets & accessories
- Audio equipment
- Office equipment (thiết bị văn phòng — printers, scanners, projectors)
- Enterprise solutions (Giải pháp doanh nghiệp — servers, networking, video-conf, digital signage, POS)
- Home appliances / home electronics (điện gia dụng / điện máy)
- Clearance / liquidation (hàng thanh lý)

Sources: https://phongvu.vn/ , https://help.phongvu.vn/ , https://phongvu.vn/p/he-thong-showroom-phong-vu

**Brands carried** (verified on homepage/laptop nav + store description):
Apple, Acer, ASUS, Dell, HP, Lenovo, MSI, Gigabyte, LG (incl. LG Gram), Samsung, Sony,
Xiaomi, Logitech, Razer, Corsair, Kingston, Microsoft. There is an "ASUS Exclusive Store
By Phong Vũ" in HCMC.

- Intel / AMD as carried component brands — **ASSUMPTION (unverified)** but near-certain given the DIY-components business.

## Store footprint

- **~40 showrooms nationwide** (official showroom page; older help copy still says "30+").
- Regional spread (all from the showroom page):
  - **North:** Hà Nội (Thái Hà, Xuân Thủy), Thái Nguyên, Bắc Ninh
  - **Central:** Đà Nẵng, Thanh Hóa, Nghệ An (Vinh), Quảng Trị, Huế, Khánh Hòa (Nha Trang),
    Ninh Thuận, Gia Lai / Quy Nhơn, Đắk Lắk
  - **South:** HCMC (15+ locations), Bình Dương, Dĩ An, Vũng Tàu, Bà Rịa, Đồng Nai, Tây Ninh,
    Long An, Bến Tre, Tiền Giang, Đồng Tháp, **Cần Thơ**
- Large-format / flagship: regional operations HQ in HCMC, dedicated regional warranty centers
  (North / Central / South), the ASUS Exclusive Store. Standard hours 8:00–21:30 daily.
- Source: https://phongvu.vn/p/he-thong-showroom-phong-vu

For the dataset we use **three regions**: North / Central / South, and a canonical set of
provinces drawn from the list above (see `generator/schema.py` for the canonical province vocabulary).

## Sales channels

- **Physical showrooms** (~40) — https://phongvu.vn/p/he-thong-showroom-phong-vu
- **E-commerce site** phongvu.vn — https://phongvu.vn/
- **Mobile app — YES.** iOS + Android; primarily a **loyalty/membership app** (scan QR to earn
  points, redeem for vouchers). Sources: https://apps.apple.com/vn/app/phong-vu/id6461310142 ,
  https://play.google.com/store/apps/details?id=vn.teko.android.consumer.phongvu
- **B2B / enterprise sales — YES, prominent.** "Giải pháp doanh nghiệp" division: servers,
  networking, video-conferencing, digital signage, POS. Source: https://help.phongvu.vn/
  - Specific strength in school/education project sales — **ASSUMPTION (unverified)**; the division
    exists, the magnitude is inferred. We model B2B as few large multi-line baskets.

Dataset channels: `in_store`, `web`, `app`, `b2b`.

## House / private-label brands

- None found. Phong Vũ sells third-party manufacturer brands only. "No house brand exists" is a
  negative finding — **ASSUMPTION (unverified)**. Dataset sets `is_private_label = false` throughout.

## Promotion mechanics (all verified for Phong Vũ specifically unless noted)

- **0% interest installments (trả góp 0%)** — flagship "Trả góp 3 KHÔNG" (no interest, no down
  payment, no fees), 3–6 month terms via banks / VNPAY.
  Sources: https://phongvu.vn/cong-nghe/uu-dai-tra-gop-3-khong-tai-phong-vu/ , https://help.phongvu.vn/chinh-sach-ban-hang/tra-gop
- **Trade-in (thu cũ đổi mới)** — laptop/PC trade-in, up to ~3M VND support, no original invoice required.
  Source: https://phongvu.vn/cong-nghe/cach-thu-cu-doi-moi-laptop/
- **Vouchers / stacking discounts** — "cộng dồn giảm giá" + extra up to 10% off paying via VNPay-QR.
  Source: https://phongvu.vn/
- **Back-to-school (mùa tựu trường)** — annual campaign, vouchers up to 5M VND on laptops/MacBooks,
  student 0-VND down payment, bundles. Source: https://phongvu.vn/p/doi-diem-thi-thpt
- **Black Friday** — 2025 "Đại chiến công nghệ", ~2 weeks (mid-Nov → early Dec), up to 70% off.
  Source: https://phongvu.vn/p/black-friday
- **11.11 (Single's Day)** — most items min 11% off, many up to 50%. Source: phongvu promo pages.
- **12.12** — "Buffet Công nghệ" year-end event. Source: phongvu promo pages.
- **Tết (Lunar New Year)** — confirmed they run Tết sales; specific mechanics **ASSUMPTION (unverified)**.

Dataset promo mechanics: `discount`, `voucher`, `installment_0pct`, `trade_in`, `bundle`.

## Modeling decisions derived from the above

- Seasonality: Tết spike (late Jan / early Feb), back-to-school laptop season (Jul–Sep),
  11.11 and 12.12 events, Black Friday folded into the 11.11–12.12 window.
- Channel mix: online (web + app) share grows over the 2-year history; B2B is a small number of
  very large baskets routed through channel `b2b`; walk-in retail dominates `in_store`.
- Return rates are category-dependent: high for components (DIY incompatibility / DOA), low for accessories.
- Amounts are in **VND** (large integers); management speaks in **tỷ** (billions of VND).
