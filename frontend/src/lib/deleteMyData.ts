import { ApiError } from "@/api/client";

// «Удалить мои данные»: a privacy action must not fail silently. Reload (which starts a fresh
// session) only once the server confirmed the delete; otherwise report why and stay put.
export async function deleteMyData(
  deleteSession: () => Promise<void>,
  reload: () => void,
  onError: (message: string) => void,
): Promise<void> {
  try {
    await deleteSession();
  } catch (err) {
    onError(
      err instanceof ApiError
        ? `Не удалось удалить данные: ${err.message}`
        : "Не удалось удалить данные. Проверьте соединение и попробуйте ещё раз.",
    );
    return;
  }
  reload();
}
