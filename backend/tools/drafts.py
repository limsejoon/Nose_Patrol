"""draft_alert / draft_farm_alert / draft_complaint: 민원 전화 문안, 문자, 농장 알림, 민원서 초안.
원인 농장(이름·방향·거리)은 문안에 넣지 않는다(명예훼손 방지). 신고 집계와 바람 정보만 쓴다.
숫자는 모두 엔진이 계산한 값을 넣는다. LLM은 쓰지 않아도 되도록 템플릿을 기본으로 둔다."""


def call_script(village, n, avg, wind):
    return (f"안녕하세요, 주민 악취 신고 서비스 냄새알림입니다. "
            f"애월읍 {village}에서 최근 1시간 동안 주민 {n}명이 악취를 신고했습니다. "
            f"평균 강도는 5점 중 {avg:.1f}점이고, {wind['label']} {wind['speed']:.0f}미터입니다. "
            f"현장 확인을 요청드립니다. 같은 내용을 문자로 보내 드리겠습니다.")


def sms(village, n, avg, wind):
    return (f"[냄새알림] {village} 최근1시간 주민 {n}명 악취 신고(평균 {avg:.1f}/5). "
            f"{wind['label']} {wind['speed']:.0f}m/s. 현장 확인 요청")


def farm_alert(village, n, wind):
    return (f"[냄새알림] 지금 {village} 주민 {n}명이 악취를 신고했어요. "
            f"{wind['label']} {wind['speed']:.0f}m/s, 농장 쪽에서 마을로 불고 있어요. 저감시설 점검을 부탁드려요.")


def complaint(village, n_total, hours, wind, history_lines):
    return (f"제목: 애월읍 {village} 축산 악취 지속 발생에 따른 현장 조치 요청\n\n"
            f"1. 발생 현황: {village}에서 {hours:.0f}시간 넘게 악취 신고가 이어졌으며, 누적 신고자는 {n_total}명입니다.\n"
            f"2. 당시 바람: {wind['label']} {wind['speed']:.0f}m/s\n"
            f"3. 참고 실측 이력(제주악취관리센터, 구역 전체): " + ("; ".join(history_lines) or "없음") + "\n"
            f"4. 요청 사항: 해당 시간대 현장 확인 및 추가 측정을 요청합니다.\n\n"
            f"※ 주민 신고 집계와 공개 실측 통계만 담았으며, 특정 사업장을 원인으로 지목하지 않습니다. 신고자 개인정보는 포함하지 않았습니다.")
