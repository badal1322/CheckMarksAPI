from locust import HttpUser, task, between

class PDFUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def upload_pdf(self):
        with open("test.pdf", "rb") as pdf:
            self.client.post("/extract/mcq", files={"file": pdf})