@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Publicando atualizacoes no GitHub Pages (alysontrindade/loja-itadigital-gestao)...
git push origin main
echo.
echo Concluido! Aguarde ~1 minuto para o GitHub Actions atualizar:
echo https://alysontrindade.github.io/loja-itadigital-gestao/
pause
