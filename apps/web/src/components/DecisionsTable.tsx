"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import type { Decision } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export default function DecisionsTable({ decisions }: { decisions: Decision[] }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "published_at", desc: true }]);
  const [filter, setFilter] = useState("");

  const columns = useMemo<ColumnDef<Decision>[]>(
    () => [
      {
        accessorKey: "published_at",
        header: "Date",
        cell: (c) => {
          const v = c.getValue<string | null>();
          return v ? new Date(v).toLocaleDateString() : "—";
        },
      },
      {
        accessorKey: "season",
        header: "Season",
        cell: (c) => <Badge variant="secondary">{c.getValue<number>()}</Badge>,
      },
      {
        accessorKey: "title",
        header: "Decision",
        cell: (c) => (
          <Link
            href={`/decisions/${c.row.original.doc_id}`}
            className="text-gray-900 dark:text-gray-100 hover:underline"
          >
            {c.getValue<string>()}
          </Link>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: decisions,
    columns,
    state: { sorting, globalFilter: filter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div className="space-y-3">
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter this page…"
        aria-label="Filter decisions"
        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded text-sm focus:outline-none focus:border-gray-400"
      />
      <div className="overflow-x-auto border border-gray-200 dark:border-gray-800 rounded-lg">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-gray-200 dark:border-gray-800">
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    onClick={h.column.getToggleSortingHandler()}
                    className="text-left text-xs text-gray-500 font-normal px-3 py-2 cursor-pointer select-none whitespace-nowrap hover:text-gray-700 dark:hover:text-gray-300"
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {{ asc: " ↑", desc: " ↓" }[h.column.getIsSorted() as string] ?? ""}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-900">
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="hover:bg-gray-50 dark:hover:bg-gray-950 transition-colors">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2 align-top">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-600">
        {table.getFilteredRowModel().rows.length} of {decisions.length} on this page · click a column to sort
      </p>
    </div>
  );
}
