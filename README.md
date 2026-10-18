# 사진 페이지

사진을 한 페이지로 보여 주는 정적 사이트입니다. `docs/` 폴더가 그대로 GitHub Pages에 올라갑니다.

## 폴더

| 경로 | 내용 |
|---|---|
| `images-full-size/` | 원본 사진. git에 올리지 않습니다(`.gitignore`). |
| `tools/build_photos.py` | 원본을 웹용 크기로 줄이고 사진 목록을 만드는 스크립트 |
| `docs/index.html` | 페이지 본문·모양·동작. 글 문구는 ①~⑤ 주석 자리에 있습니다. |
| `docs/img/800·1600·2560/` | 스크립트가 만든 사진(긴 변 기준 px) |
| `docs/photos.js` | 스크립트가 만든 사진 목록 |
| `docs/og.jpg` | 카카오톡 등에 링크를 붙였을 때 보이는 미리보기 사진 |

## 사진을 넣거나 뺐을 때

`images-full-size/`에 사진을 넣거나 뺀 다음 실행합니다. 바뀐 사진만 다시 만들고, 뺀 사진은 `docs/img`에서도 지웁니다.

```bash
uv run tools/build_photos.py
```

화질·크기 설정(`SIZES`)을 바꿨다면 전부 다시 만듭니다.

```bash
uv run tools/build_photos.py --force
```

- 필요한 패키지(Pillow)는 스크립트 머리말에 적혀 있어 `uv`가 알아서 준비합니다.
- 순서는 촬영 시각 → 파일 이름입니다.
- 세로 사진은 바로 세우고, EXIF(촬영 위치 포함)는 모두 지웁니다.
- 미리보기 사진은 스크립트의 `OG_PHOTO`에서 바꿉니다.

## 내 컴퓨터에서 보기

```bash
uv run python -m http.server 4387 --bind 127.0.0.1 --directory docs
```

브라우저에서 <http://localhost:4387> 을 엽니다.
