import { ChevronLeft, ChevronRight } from "lucide-react";
import { int } from "./format";

export function Pager({
  page,
  total,
  size,
  setPage,
}: {
  page: number;
  total: number;
  size: number;
  setPage: (page: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${int((page - 1) * size + 1)}–${int(Math.min(page * size, total))} de ${int(total)}`
          : "Nenhum registro"}
      </span>
      <div>
        <button
          className="icon-button"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
          aria-label="Página anterior"
        >
          <ChevronLeft size={18} />
        </button>
        <span>Página {page}</span>
        <button
          className="icon-button"
          disabled={page * size >= total}
          onClick={() => setPage(page + 1)}
          aria-label="Próxima página"
        >
          <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
}
