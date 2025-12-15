import base64
import json
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import torch
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL_ID = "Qwen/Qwen2.5-7B"
KEY_B64 = "mJd8h4w8m7Gkq+2q0wzvWZg0YH0p4o8Uu1Q1l9uXcH0="
KEY = base64.b64decode(KEY_B64)
AES = AESGCM(KEY)


def _hf_kwargs(model_id: str) -> Dict[str, Any]:
    if model_id.lower().startswith("qwen/"):
        return {"trust_remote_code": True}
    return {}

j
@dataclass
class WireMessage:
    blob_b64: str
    aad: Dict[str, Any]


class TokenizedEncryptedLLMDemo:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.hf_kwargs = _hf_kwargs(model_id)
        self.client_tokenizer = AutoTokenizer.from_pretrained(model_id, **self.hf_kwargs)
        self.server_tokenizer = AutoTokenizer.from_pretrained(model_id, **self.hf_kwargs)
        self.server_model = AutoModelForCausalLM.from_pretrained(model_id, **self.hf_kwargs)
        self.server_model.eval()

    def client_tokenize(self, text: str) -> Dict[str, Any]:
        if "instruct" in self.model_id.lower() and hasattr(self.client_tokenizer, "apply_chat_template"):
            text = self.client_tokenizer.apply_chat_template(
                [{"role": "user", "content": text}],
                tokenize=False,
                add_generation_prompt=True,
            )
            add_special_tokens = True
        else:
            add_special_tokens = True

        enc = self.client_tokenizer(
            text,
            return_tensors=None,
            add_special_tokens=add_special_tokens,
            return_attention_mask=True,
        )

        input_ids = enc["input_ids"]
        attn = enc.get("attention_mask")

        if input_ids and isinstance(input_ids[0], list):
            input_ids = input_ids[0]
        if attn and isinstance(attn[0], list):
            attn = attn[0]
        if attn is None:
            attn = [1] * len(input_ids)

        return {
            "model_id": self.model_id,
            "tokenizer_name": self.client_tokenizer.name_or_path,
            "tokens": input_ids,
            "attention_mask": attn,
        }

    def client_encrypt(self, payload: Dict[str, Any], aad: Dict[str, Any]) -> WireMessage:
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        nonce = secrets.token_bytes(12)
        aad_bytes = json.dumps(aad, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ciphertext = AES.encrypt(nonce, plaintext, aad_bytes)
        blob_b64 = base64.b64encode(nonce + ciphertext).decode("ascii")
        return WireMessage(blob_b64=blob_b64, aad=aad)

    def server_decrypt(self, msg: WireMessage) -> Dict[str, Any]:
        blob = base64.b64decode(msg.blob_b64)
        nonce, ciphertext = blob[:12], blob[12:]
        aad_bytes = json.dumps(msg.aad, separators=(",", ":"), sort_keys=True).encode("utf-8")
        plaintext = AES.decrypt(nonce, ciphertext, aad_bytes)
        return json.loads(plaintext.decode("utf-8"))

    @torch.inference_mode()
    def server_generate(self, token_ids: List[int], attention_mask: Optional[List[int]] = None, max_new_tokens: int = 25) -> Dict[str, Any]:
        input_ids = torch.tensor([token_ids], dtype=torch.long)
        if attention_mask is None:
            attention_mask = [1] * len(token_ids)
        attn = torch.tensor([attention_mask], dtype=torch.long)

        out_ids = self.server_model.generate(
            input_ids=input_ids,
            attention_mask=attn,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )

        prompt_text = self.server_tokenizer.decode(input_ids[0], skip_special_tokens=False)
        full_text = self.server_tokenizer.decode(out_ids[0], skip_special_tokens=False)
        generated_only = full_text[len(prompt_text):]

        return {
            "prompt_preview": prompt_text,
            "generated_text": generated_only,
            "full_text": full_text,
            "input_token_count": len(token_ids),
            "output_token_count": int(out_ids.shape[-1]),
        }

    def server_infer(self, msg: WireMessage, max_new_tokens: int = 25) -> Dict[str, Any]:
        payload = self.server_decrypt(msg)
        if payload.get("model_id") != self.model_id:
            return {"ok": False, "error": f"Model mismatch: got {payload.get('model_id')} expected {self.model_id}"}

        tokens = payload["tokens"]
        attn = payload.get("attention_mask")
        result = self.server_generate(tokens, attn, max_new_tokens=max_new_tokens)

        return {
            "ok": True,
            "aad_seen_by_server": msg.aad,
            "llm_result": result,
        }

    def interactive(self):
        print("Type 'exit' to quit.")
        while True:
            try:
                text = input(">>> ").strip()
                if not text:
                    continue
                if text.lower() in {"exit", "quit"}:
                    break

                payload = self.client_tokenize(text)
                aad = {"client_id": "client-xyz", "policy_id": "policy-abc", "content_type": "token_ids_v1"}
                wire = self.client_encrypt(payload, aad)
                resp = self.server_infer(wire, max_new_tokens=25)
                if not resp.get("ok"):
                    print(resp)
                    continue
                print(resp["llm_result"]["generated_text"])

            except KeyboardInterrupt:
                break


if __name__ == "__main__":
    TokenizedEncryptedLLMDemo(MODEL_ID).interactive()
