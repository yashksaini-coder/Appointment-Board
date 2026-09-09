from datetime import date, timedelta

DAY = str(date.today() + timedelta(days=3))


def make(client, **overrides):
    payload = {
        "title": "Team standup",
        "description": "Daily sync",
        "appointment_date": DAY,
        "start_time": "09:00",
        "end_time": "09:30",
    } | overrides
    return client.post("/api/appointments", json=payload)


def test_create_and_list(client):
    assert make(client).status_code == 201
    body = client.get("/api/appointments").json()
    assert [a["title"] for a in body] == ["Team standup"]
    assert body[0]["status"] == "scheduled"
    assert body[0]["start_time"] == "09:00"


def test_title_is_required(client):
    res = make(client, title="   ")
    assert res.status_code == 422
    assert "title" in res.json()["detail"].lower()


def test_end_must_follow_start(client):
    res = make(client, start_time="11:00", end_time="10:00")
    assert res.status_code == 422
    assert "after start time" in res.json()["detail"]


def test_overlapping_slot_is_rejected(client):
    make(client, start_time="10:00", end_time="11:00")
    res = make(client, title="Clash", start_time="10:30", end_time="11:30")
    assert res.status_code == 409
    assert "already booked" in res.json()["detail"]


def test_back_to_back_slots_are_allowed(client):
    make(client, start_time="10:00", end_time="11:00")
    assert make(client, title="Next", start_time="11:00", end_time="12:00").status_code == 201


def test_same_time_on_another_day_is_allowed(client):
    make(client, start_time="10:00", end_time="11:00")
    other_day = str(date.today() + timedelta(days=4))
    assert make(client, title="Tomorrow", appointment_date=other_day).status_code == 201


def test_cancelling_frees_the_slot(client):
    first = make(client, start_time="10:00", end_time="11:00").json()
    assert make(client, title="Clash", start_time="10:00", end_time="11:00").status_code == 409

    assert client.post(f"/api/appointments/{first['id']}/cancel").json()["status"] == "cancelled"
    assert make(client, title="Reuse", start_time="10:00", end_time="11:00").status_code == 201


def test_completed_appointment_still_holds_its_slot(client):
    first = make(client, start_time="10:00", end_time="11:00").json()
    client.post(f"/api/appointments/{first['id']}/complete")
    assert make(client, title="Clash", start_time="10:00", end_time="11:00").status_code == 409


def test_edit_moves_the_appointment(client):
    appt = make(client).json()
    res = client.patch(f"/api/appointments/{appt['id']}", json={"start_time": "14:00", "end_time": "15:00"})
    assert res.status_code == 200
    assert res.json()["start_time"] == "14:00"


def test_edit_into_a_taken_slot_is_rejected(client):
    make(client, start_time="10:00", end_time="11:00")
    movable = make(client, title="Movable", start_time="14:00", end_time="15:00").json()
    res = client.patch(f"/api/appointments/{movable['id']}", json={"start_time": "10:30", "end_time": "11:30"})
    assert res.status_code == 409


def test_edit_keeping_its_own_slot_is_fine(client):
    appt = make(client, start_time="10:00", end_time="11:00").json()
    res = client.patch(f"/api/appointments/{appt['id']}", json={"title": "Renamed"})
    assert res.status_code == 200 and res.json()["title"] == "Renamed"


def test_cancelled_appointments_are_terminal(client):
    appt = make(client).json()
    client.post(f"/api/appointments/{appt['id']}/cancel")
    assert client.post(f"/api/appointments/{appt['id']}/complete").status_code == 409
    assert client.patch(f"/api/appointments/{appt['id']}", json={"title": "x"}).status_code == 409


def test_filters(client):
    make(client, start_time="09:00", end_time="09:30")
    later = make(client, title="Later", start_time="10:00", end_time="11:00").json()
    other_day = str(date.today() + timedelta(days=4))
    make(client, title="Other day", appointment_date=other_day)
    client.post(f"/api/appointments/{later['id']}/cancel")

    assert len(client.get("/api/appointments", params={"date": DAY}).json()) == 2
    assert len(client.get("/api/appointments", params={"status": "cancelled"}).json()) == 1
    assert len(client.get("/api/appointments", params={"date": other_day, "status": "scheduled"}).json()) == 1
    assert client.get("/api/appointments", params={"status": "bogus"}).status_code == 400


def test_missing_appointment_is_404(client):
    assert client.get("/api/appointments/9999").status_code == 404
