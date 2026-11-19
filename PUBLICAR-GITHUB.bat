@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===============================================================
echo  Publicando atualizacoes no GitHub Pages (ItaDigital Gestao)
echo ===============================================================
echo.
git push origin main
if %ERRORLEVEL% equ 0 (
    echo.
    echo ===============================================================
    echo  [SUCESSO] Arquivos enviados com sucesso para o GitHub!
    echo  Aguarde cerca de 1 minuto e recarregue a pagina (Ctrl + F5):
    echo  https://alysontrindade.github.io/loja-itadigital-gestao/
    echo ===============================================================
) else (
    echo.
    echo ===============================================================
    echo  [ERRO] Ocorreu uma falha no envio do git push.
    echo ===============================================================
)
echo.
pause
