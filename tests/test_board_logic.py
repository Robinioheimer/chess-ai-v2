import chess


def test_start_position_has_twenty_legal_moves():
    board = chess.Board()
    assert board.legal_moves.count() == 20


def test_uci_move_is_legal_in_start_position():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    assert move in board.legal_moves
