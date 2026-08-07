"use client";

import { FormEvent, useEffect, useState } from "react";
// import AppShell from "@/components/layout/AppShell";
import { feedErpOrders, listErpOrders, type ErpOrder } from "@/lib/api";

const emptyForm: ErpOrder = {
  order_number: "ORD-10001",
  customer_id: "CUST-2048",
  customer_email: "alice.johnson@email.com",
  status: "processing",
  total_amount: 189.5,
  currency: "USD",
  vendor_id: "VENDOR-17",
  tracking_number: null,
  shipping_address: {
    street: "742 Evergreen Terrace",
    city: "Springfield",
    state: "IL",
    zip: "62704",
    country: "US",
  },
  items: [
    { sku: "SKU-8811", name: "Noise Cancelling Headphones", qty: 1, price: 149.5 },
    { sku: "SKU-2203", name: "USB-C Cable 2m", qty: 2, price: 20 },
  ],
};

export default function ErpOrdersPage() {
  const [rows, setRows] = useState<ErpOrder[]>([]);
  const [orderNumber, setOrderNumber] = useState("");
  const [loading, setLoading] = useState(true);
  const [feeding, setFeeding] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<ErpOrder>({ ...emptyForm });
  const [itemsJson, setItemsJson] = useState(JSON.stringify(emptyForm.items, null, 2));
  const [addressJson, setAddressJson] = useState(
    JSON.stringify(emptyForm.shipping_address, null, 2)
  );

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listErpOrders({
        order_number: orderNumber || undefined,
        limit: 50,
      });
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load ERP orders");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onFeed(e: FormEvent) {
    e.preventDefault();
    setFeeding(true);
    setMessage(null);
    setError(null);
    try {
      const shipping_address = JSON.parse(addressJson);
      const items = JSON.parse(itemsJson);
      const payload: ErpOrder = {
        ...form,
        total_amount: Number(form.total_amount || 0),
        shipping_address,
        items,
        tracking_number: form.tracking_number || null,
      };

      const res = await feedErpOrders([payload]);

      // Handle backend duplicate-aware response shapes
      const results = res?.results || res?.orders || res?.items || [];
      const first = Array.isArray(results) ? results[0] : null;
      const reason = first?.reason || res?.reason;
      const created = res?.created_count ?? res?.created ?? null;

      if (reason === "already exists" || first?.status === "exists") {
        setMessage(`Order ${payload.order_number} already exists (duplicate not inserted)`);
      } else if (created === 0) {
        setMessage(`No new order created for ${payload.order_number}`);
      } else {
        setMessage(`Fed order ${payload.order_number} successfully`);
      }

      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feed failed");
    } finally {
      setFeeding(false);
    }
  }

  return (
    <>
      <div className="mb-6">
        <h2 className="text-2xl font-semibold">ERP Orders</h2>
        <p className="text-sm text-slate-400">
          Feed full ERP records so investigation reports include complete details
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <form onSubmit={onFeed} className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-5">
          <h3 className="font-medium">Feed full order</h3>

          {(
            [
              ["order_number", form.order_number],
              ["customer_id", form.customer_id || ""],
              ["customer_email", form.customer_email || ""],
              ["status", form.status || "processing"],
              ["currency", form.currency || "USD"],
              ["vendor_id", form.vendor_id || ""],
              ["tracking_number", form.tracking_number || ""],
            ] as Array<[keyof ErpOrder | string, string]>
          ).map(([key, value]) => (
            <input
              key={String(key)}
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm"
              value={value}
              placeholder={String(key)}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              required={key === "order_number"}
            />
          ))}

          <input
            type="number"
            step="0.01"
            className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm"
            value={form.total_amount ?? 0}
            onChange={(e) => setForm({ ...form, total_amount: Number(e.target.value) })}
            placeholder="total_amount"
          />

          <div>
            <label className="mb-1 block text-xs text-slate-400">shipping_address (JSON)</label>
            <textarea
              className="min-h-28 w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 font-mono text-xs"
              value={addressJson}
              onChange={(e) => setAddressJson(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-400">items (JSON array)</label>
            <textarea
              className="min-h-28 w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 font-mono text-xs"
              value={itemsJson}
              onChange={(e) => setItemsJson(e.target.value)}
            />
          </div>

          {message && <p className="text-sm text-emerald-300">{message}</p>}
          {error && <p className="text-sm text-rose-300">{error}</p>}

          <button
            type="submit"
            disabled={feeding}
            className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-60"
          >
            {feeding ? "Feeding..." : "Feed full order"}
          </button>
        </form>

        <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
          <div className="mb-3 flex gap-2">
            <input
              value={orderNumber}
              onChange={(e) => setOrderNumber(e.target.value)}
              placeholder="Filter order number"
              className="flex-1 rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm"
            />
            <button
              onClick={load}
              className="rounded-xl border border-white/10 px-3 py-2 text-sm hover:bg-white/5"
            >
              Search
            </button>
          </div>

          {loading ? (
            <p className="text-slate-400">Loading...</p>
          ) : (
            <div className="space-y-3">
              {rows.map((r) => (
                <div
                  key={`${r.order_number}-${r.id || ""}`}
                  className="rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm"
                >
                  <p className="font-medium text-slate-100">{r.order_number}</p>
                  <p className="text-slate-300">Status: {r.status}</p>
                  <p className="text-slate-300">Customer: {r.customer_id} · {r.customer_email}</p>
                  <p className="text-slate-300">Vendor: {r.vendor_id}</p>
                  <p className="text-slate-300">
                    Amount: {r.total_amount} {r.currency}
                  </p>
                  <p className="text-slate-300">Tracking: {r.tracking_number || "null"}</p>
                  <p className="mt-2 text-xs text-slate-400">
                    Address: {JSON.stringify(r.shipping_address)}
                  </p>
                  <p className="text-xs text-slate-400">Items: {JSON.stringify(r.items)}</p>
                </div>
              ))}
              {rows.length === 0 && <p className="text-slate-400">No ERP orders found.</p>}
            </div>
          )}
        </div>
      </div>
    </>
  );
}