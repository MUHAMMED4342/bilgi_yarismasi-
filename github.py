import os
import subprocess
import sys


def run_cmd(command):
  """Komutları çalıştırır ve hata alıp almadığını kontrol eder."""
  result = subprocess.run(
      command, capture_output=True, text=True, encoding="utf-8"
  )
  if result.returncode != 0:
    print(f"Hata oluştu: {result.stderr.strip()}")
    return False
  print(result.stdout.strip())
  return True


def main():
  print("--- GitHub Otomatik Push Asistanı ---")

  # 1. Proje adı al
  repo_name = (
      input(
          "Oluşturulacak veya bağlanacak GitHub depo (repo) adını girin (Boş"
          " bırakırsanız klasör adı kullanılır): "
      )
      .strip()
  )
  if not repo_name:
    repo_name = os.path.basename(os.getcwd())

  # 2. Gizlilik durumu
  is_private = (
      input("Depo gizli (private) olsun mu? (E/H): ").strip().lower() == "e"
  )
  visibility = "--private" if is_private else "--public"

  # 3. Git başlatılmamışsa başlat
  if not os.path.exists(".git"):
    print("Git deposu başlatılıyor...")
    if not run_cmd(["git", "init"]):
      return
  else:
    print("Mevcut bir Git deposu algılandı.")

  # 4. Gitignore hariç her şeyi ekle
  print("Dosyalar ekleniyor (.gitignore hariç tutuluyor)...")
  if not run_cmd(["git", "add", "."]):
    return

  # 5. Commit yap
  commit_msg = (
      input("Commit mesajı girin (Varsayılan: 'Otomatik güncelleme'): ").strip()
      or "Otomatik güncelleme"
  )
  # Değişiklik yoksa hata vermesini engellemek için kontrol
  status_check = subprocess.run(
      ["git", "status", "--porcelain"], capture_output=True, text=True
  )
  if status_check.stdout.strip():
    run_cmd(["git", "commit", "-m", commit_msg])
  else:
    print("Commit edilecek yeni değişiklik yok, mevcut durumla devam ediliyor.")

  # 6. GitHub'da repo var mı kontrol et veya oluştur
  print("GitHub deposu kontrol ediliyor/oluşturuluyor...")
  remote_check = subprocess.run(
      ["git", "remote", "get-url", "origin"], capture_output=True, text=True
  )

  if remote_check.returncode != 0:
    # Remote yok, GitHub CLI ile yeni repo oluşturalım
    create_repo_cmd = [
        "gh",
        "repo",
        "create",
        repo_name,
        visibility,
        "--source=.",
        "--remote=origin",
        "--push",
    ]
    print(f"GitHub'da '{repo_name}' adında depo oluşturulup bağlanıyor...")
    if run_cmd(create_repo_cmd):
      print(f"\nİşlem tamam! Depo başarıyla GitHub'a yüklendi.")
    else:
      print(
          "\nGitHub'da depo oluşturulamadı. 'gh auth login' yapıp yapmadığını"
          " kontrol et."
      )
  else:
    print(
        "Mevcut uzak depo (origin) bulundu, değişiklikler gönderiliyor (push)..."
    )
    # Ana dal adını tespit et (main veya master)
    branch_res = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    )
    branch = branch_res.stdout.strip() or "main"

    if run_cmd(["git", "push", "-u", "origin", branch]):
      print(f"\nİşlem tamam! Kodlar başarıyla güncellendi.")


if __name__ == "__main__":
  main()