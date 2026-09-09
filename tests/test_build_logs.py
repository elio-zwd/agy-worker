"""验证真实构建器的非标准诊断，不让关键行在摘要中遗漏。"""
from agy_worker.logs import extract


def test_vite_diagnostics(tmp_path):
    raw=tmp_path/'raw.log'
    raw.write_text('Could not resolve "module.js"\n(!) dynamic import will not move module into another chunk.\n',encoding='utf-8')
    result=extract(raw,tmp_path/'clean.log')
    assert len(result['errors'])==1
    assert len(result['warnings'])==1
    assert result['errors'][0]['evidence']['start_line']==1
