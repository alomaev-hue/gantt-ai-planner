import { ApiError } from "@/api/client";
import { deleteMyData } from "./deleteMyData";

test("reloads after the data is deleted", async () => {
  const reload = vi.fn();
  const onError = vi.fn();
  await deleteMyData(async () => undefined, reload, onError);
  expect(reload).toHaveBeenCalledOnce();
  expect(onError).not.toHaveBeenCalled();
});

test("a failed delete is reported and does NOT reload as if it had worked", async () => {
  const reload = vi.fn();
  const onError = vi.fn();
  await deleteMyData(
    async () => {
      throw new ApiError(500, "http_error", "Ошибка 500");
    },
    reload,
    onError,
  );
  expect(reload).not.toHaveBeenCalled();
  expect(onError).toHaveBeenCalledWith("Не удалось удалить данные: Ошибка 500");
});

test("a network failure is reported too", async () => {
  const onError = vi.fn();
  await deleteMyData(async () => Promise.reject(new TypeError("Failed to fetch")), vi.fn(), onError);
  expect(onError).toHaveBeenCalledWith("Не удалось удалить данные. Проверьте соединение и попробуйте ещё раз.");
});
